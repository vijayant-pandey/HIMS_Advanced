"""Read PostgreSQL's query plans for the high-volume queries (spec 28.6; HIMS-DATA-002).

For each query in ``queries.QUERIES``:

1. ``EXPLAIN (ANALYZE, BUFFERS)`` runs it as the app would and records the plan: which indexes
   were used, which tables were read whole, how long it took and how many rows it read.
2. If the expected index was not used and the table is small, a full read is simply quicker, so
   the plan is asked again with full reads switched off: the index must then be chosen, which
   proves it is ready for when the table grows.
3. A query passes when its index serves it and, on a table of 10,000 rows or more, it finishes
   within its time budget.

Only SELECT statements are explained, so nothing is changed. The plans themselves are not kept:
only index names, table names, timings and row counts.
"""

import time

from django.db import connection, transaction

from .queries import QUERIES, QueryCheck, pick_samples

# Below this many rows PostgreSQL rightly reads a table whole instead of using an index.
SMALL_TABLE_ROWS = 10_000
# A query returning at least this share of a table is quickest read whole, whatever its size.
MOST_OF_TABLE = 0.2


def _walk(node: dict, found: dict) -> None:
    index = node.get("Index Name")
    if index:
        found["indexes"].add(index)
    if node.get("Node Type") == "Seq Scan" and node.get("Relation Name"):
        found["full_reads"].add(node["Relation Name"])
    for child in node.get("Plans", []):
        _walk(child, found)


def _explain(sql: str, params, *, analyze: bool) -> dict:
    options = "ANALYZE, BUFFERS, FORMAT JSON" if analyze else "FORMAT JSON"
    with connection.cursor() as cursor:
        cursor.execute(f"EXPLAIN ({options}) {sql}", params)
        (document,) = cursor.fetchone()
    if isinstance(document, str):  # pragma: no cover - psycopg normally decodes JSON
        import json

        document = json.loads(document)
    top = document[0]
    found = {"indexes": set(), "full_reads": set()}
    _walk(top["Plan"], found)
    return {
        "indexes": sorted(found["indexes"]),
        "full_reads": sorted(found["full_reads"]),
        "ms": round(top.get("Execution Time", 0.0), 2),
        "rows": int(top["Plan"].get("Actual Rows", 0)) if analyze else None,
    }


def _explain_without_full_reads(sql: str, params) -> dict:
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL enable_seqscan = off")
        return _explain(sql, params, analyze=False)


def table_rows(tables) -> dict[str, int]:
    """PostgreSQL's own row estimate per table (kept up to date by autovacuum and ANALYZE)."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname, GREATEST(reltuples, 0)::bigint FROM pg_class "
            "WHERE relkind IN ('r', 'p') AND relname = ANY(%s)",
            [sorted(set(tables))],
        )
        return dict(cursor.fetchall())


def _served(check: QueryCheck, indexes) -> bool:
    return any(
        name.startswith(wanted) if wanted.endswith("_") else name == wanted
        for name in indexes
        for wanted in (*check.indexes, *check.also)
    )


def check_query(check: QueryCheck, samples: dict, rows_in_table: int) -> dict:
    sql, params = check.build(samples).query.sql_with_params()
    plan = _explain(sql, params, analyze=True)
    result = {
        "key": check.key,
        "label": check.label,
        "table": check.table,
        "table_rows": rows_in_table,
        "expected_indexes": list(check.indexes),
        "indexes_used": plan["indexes"],
        "full_reads": plan["full_reads"],
        "ms": plan["ms"],
        "budget_ms": check.budget_ms,
        "rows": plan["rows"],
        "passed": True,
        "detail": "",
    }
    problems = []
    returns_most = plan["rows"] is not None and plan["rows"] >= MOST_OF_TABLE * rows_in_table > 0
    if not _served(check, plan["indexes"]):
        if returns_most and rows_in_table >= SMALL_TABLE_ROWS:
            result["detail"] = (
                f"Returns {plan['rows']:,} of {rows_in_table:,} rows: reading the table whole "
                "is the quickest way to get most of it."
            )
        elif check.batch and plan["ms"] <= check.budget_ms:
            forced = _explain_without_full_reads(sql, params)
            if _served(check, forced["indexes"]):
                result["detail"] = (
                    "Most rows are past the cut-off, so reading from the start fills a batch at "
                    "once; the index is chosen once full reads are ruled out."
                )
            else:
                problems.append("No index serves this query once full reads are ruled out.")
        elif rows_in_table >= SMALL_TABLE_ROWS:
            problems.append(
                f"Reads {', '.join(plan['full_reads']) or 'the table'} without the expected "
                f"index ({rows_in_table:,} rows)."
            )
        elif returns_most:
            result["detail"] = (
                f"Small table ({rows_in_table:,} rows) and the query returns most of it: read "
                "whole."
            )
        else:
            forced = _explain_without_full_reads(sql, params)
            if _served(check, forced["indexes"]):
                result["detail"] = (
                    f"Small table ({rows_in_table:,} rows): read whole, which is quicker at this "
                    "size; the index is chosen once full reads are ruled out."
                )
            else:
                problems.append(
                    "No index serves this query, even with full reads ruled out "
                    f"(used: {', '.join(forced['indexes']) or 'none'})."
                )
    # Timings of a few rows are noise (a busy PC, a cold cache); the budget is for real volume.
    if plan["ms"] > check.budget_ms and rows_in_table >= SMALL_TABLE_ROWS:
        problems.append(f"Took {plan['ms']:.1f} ms; the budget is {check.budget_ms:.0f} ms.")
    if problems:
        result["passed"] = False
        result["detail"] = " ".join(problems)
    return result


def run_index_check(queries=QUERIES) -> tuple[list[dict], dict[str, int]]:
    """Every registered query's plan, and the row estimate of each table involved."""
    samples = pick_samples()
    rows = table_rows(check.table for check in queries)
    results = []
    for check in queries:
        started = time.monotonic()
        try:
            with transaction.atomic():  # a failed query must not spoil the ones after it
                results.append(check_query(check, samples, rows.get(check.table, 0)))
        except Exception as exc:  # one broken query must not hide the others
            results.append(
                {
                    "key": check.key,
                    "label": check.label,
                    "table": check.table,
                    "table_rows": rows.get(check.table, 0),
                    "expected_indexes": list(check.indexes),
                    "indexes_used": [],
                    "full_reads": [],
                    "ms": round((time.monotonic() - started) * 1000, 2),
                    "budget_ms": check.budget_ms,
                    "rows": None,
                    "passed": False,
                    "detail": f"Could not be checked: {type(exc).__name__}",
                }
            )
    return results, rows
