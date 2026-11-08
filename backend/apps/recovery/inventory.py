"""What a database holds, described without its contents (HIMS-OPS-009).

The same description is taken from the live database at backup time (inside the exact snapshot
``pg_dump`` copies) and from the restored copy during a drill; the drill compares the two. Each
table is described by its row count and a fingerprint of all its rows, so a single changed or
missing row is noticed without any record content leaving the database.
"""

import re

from psycopg import sql

AUDIT_TABLES = ("audit_events", "audit_chain_entries", "audit_integrity_checks")
# PostgreSQL prints a re-read rule with its casts and brackets placed differently (e.g.
# "(ARRAY['a'::character varying])::text[]" becomes "ARRAY[('a'::character varying)::text]").
_CAST = re.compile(r"::[a-z_ ]+(\[\])?")
_LAYOUT = re.compile(r"[()\s]")


def same_rule(definition: str) -> str:
    """A rule or index definition with casts, brackets and spaces left out, so the same rule
    compares equal before and after a restore (columns, operators and values still count)."""
    return _LAYOUT.sub("", _CAST.sub("", definition))


def _rows(cursor, query, params=None) -> list[tuple]:
    cursor.execute(query, params)
    return cursor.fetchall()


def _table_fingerprints(cursor) -> dict[str, dict]:
    tables = [
        name
        for (name,) in _rows(
            cursor, "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1"
        )
    ]
    described = {}
    for table in tables:
        query = sql.SQL(
            "SELECT count(*), coalesce(md5(string_agg(h, '' ORDER BY h)), '') "
            "FROM (SELECT md5(t::text) AS h FROM {} AS t) AS rows"
        ).format(sql.Identifier(table))
        count, fingerprint = _rows(cursor, query)[0]
        described[table] = {"rows": count, "fingerprint": fingerprint}
    return described


def _audit(cursor) -> dict:
    links, last_sequence = _rows(
        cursor, "SELECT count(*), coalesce(max(sequence), 0) FROM audit_chain_entries"
    )[0]
    head = _rows(
        cursor, "SELECT entry_hash FROM audit_chain_entries WHERE sequence = %s", [last_sequence]
    )
    unknown_actors = _rows(
        cursor,
        "SELECT count(*) FROM audit_events e WHERE e.actor_type = 'user' "
        "AND e.actor_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id = e.actor_id)",
    )[0][0]
    links_without_event = _rows(
        cursor,
        "SELECT count(*) FROM audit_chain_entries c "
        "WHERE NOT EXISTS (SELECT 1 FROM audit_events e WHERE e.id = c.event_id)",
    )[0][0]
    return {
        "events": _rows(cursor, "SELECT count(*) FROM audit_events")[0][0],
        "links": links,
        "last_sequence": last_sequence,
        "chain_head": head[0][0] if head else "",
        "events_with_unknown_actor": unknown_actors,
        "links_without_event": links_without_event,
    }


def describe(cursor) -> dict:
    """Describe the database ``cursor`` is connected to (run inside one snapshot)."""
    cursor.execute("SET TIME ZONE 'UTC'")  # rows print the same way in both sessions
    return {
        "server_version": _rows(cursor, "SHOW server_version")[0][0],
        "tables": _table_fingerprints(cursor),
        "migrations": [
            f"{app}.{name}"
            for app, name in _rows(cursor, "SELECT app, name FROM django_migrations ORDER BY 1, 2")
        ],
        "constraints": {
            f"{table}.{name}": {"type": kind, "valid": valid, "rule": same_rule(definition)}
            for table, name, kind, valid, definition in _rows(
                cursor,
                "SELECT conrelid::regclass::text, conname, contype, convalidated, "
                "pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE connamespace = 'public'::regnamespace AND conrelid <> 0 ORDER BY 1, 2",
            )
        },
        "triggers": {
            f"{table}.{name}": enabled
            for table, name, enabled in _rows(
                cursor,
                "SELECT tgrelid::regclass::text, tgname, tgenabled::text FROM pg_trigger "
                "WHERE NOT tgisinternal ORDER BY 1, 2",
            )
        },
        "indexes": {
            name: same_rule(definition)
            for name, definition in _rows(
                cursor,
                "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' ORDER BY 1",
            )
        },
        "extensions": [name for (name,) in _rows(cursor, "SELECT extname FROM pg_extension")],
        "sequences": dict(
            _rows(
                cursor,
                "SELECT sequencename, last_value FROM pg_sequences WHERE schemaname = 'public'",
            )
        ),
        "audit": _audit(cursor),
        "documents": {
            str(document_id): {"file": file, "sha256": sha256, "bytes": size}
            for document_id, file, sha256, size in _rows(
                cursor, "SELECT id, file, sha256, size_bytes FROM staff_documents"
            )
        },
    }


def encrypted_samples(cursor) -> list[str]:
    """A few values encrypted with this deployment's keys (authenticator secrets, unsent
    messages), to prove the restored copy can still be read with the keys kept outside it."""
    return [
        value
        for query in (
            "SELECT secret_encrypted FROM user_mfa_devices ORDER BY id LIMIT 3",
            "SELECT body_encrypted FROM notifications WHERE body_encrypted <> '' "
            "ORDER BY created_at LIMIT 3",
        )
        for (value,) in _rows(cursor, query)
    ]
