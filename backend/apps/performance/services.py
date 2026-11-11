"""Run and record performance checks (spec 18, 28.6; HIMS-DATA-002, HIMS-OPS-017).

* ``run_index_check``: the query plans of the high-volume queries, on this database. Reads only;
  safe in any environment, so people with ``platform.performance.manage`` can run it from the
  app or the console.
* ``run_response_times``: the response time of the main screens, measured in this process inside
  a transaction that is rolled back. Developer PC and test runs only (command line).
* ``run_volume_check``: both, on a throw-away copy (``hims_volume``) filled with production-like
  synthetic records, then the copy is removed. The results are recorded here, in the hospital's
  own database, so they show on the Performance screen. Developer PC only.

Every result is a PerformanceCheck row (append-only) and an audit event.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

import psycopg
from django.conf import settings
from django.db import connection
from django.utils import timezone

from apps.audit.services import AuditAction, record_audit_event
from common.environment import LOCAL_ENVIRONMENTS
from common.exceptions import ConflictError
from common.log_safety import scrub

from . import plans, timings
from .models import PerformanceCheck
from .volume import MAIN_TABLES, VOLUME_DATABASE

# One check at a time per database (PostgreSQL advisory lock, released at the end).
_CHECK_LOCK = 7_406_017


class PerformanceError(Exception):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def can_run_here() -> bool:
    return settings.HIMS_ENVIRONMENT in LOCAL_ENVIRONMENTS


def _require_local(what: str) -> None:
    if not can_run_here():
        raise PerformanceError(
            f"{what} runs only on a developer PC. In hosted environments the response times "
            "come from the monitoring of real traffic and from the load test (HIMS-OPS-021)."
        )


def dataset() -> dict[str, int]:
    """Approximate rows in the main tables now (PostgreSQL's estimate; no counting)."""
    return plans.table_rows(MAIN_TABLES)


def record(
    *,
    kind: str,
    trigger: str,
    started_at,
    results: list[dict],
    rows: dict[str, int],
    database: str | None = None,
    actor=None,
    request=None,
) -> PerformanceCheck:
    problems = sum(1 for item in results if not item.get("passed"))
    if kind == PerformanceCheck.Kind.INDEXES:
        summary = f"{len(results) - problems} of {len(results)} queries use their index in time"
    else:
        summary = f"{len(results) - problems} of {len(results)} screens within their target"
    check = PerformanceCheck.objects.create(
        kind=kind,
        started_at=started_at,
        trigger=trigger,
        requested_by_id=getattr(actor, "pk", None),
        outcome=PerformanceCheck.Outcome.FAILED if problems else PerformanceCheck.Outcome.PASSED,
        database=database or connection.settings_dict["NAME"],
        environment=settings.HIMS_ENVIRONMENT,
        release=getattr(settings, "HIMS_RELEASE", ""),
        dataset=rows,
        dataset_rows=sum(rows.values()),
        results=results,
        problem_count=problems,
        summary=summary,
    )
    record_audit_event(
        action=AuditAction.PERFORMANCE_CHECK_RUN,
        resource_type="performance_check",
        resource_id=check.pk,
        actor=actor,
        request=request,
        metadata={
            "kind": kind,
            "trigger": trigger,
            "outcome": check.outcome,
            "problems": problems,
            "database": check.database,
            "rows": check.dataset_rows,
        },
    )
    return check


class _OneAtATime:
    def __enter__(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [_CHECK_LOCK])
            (locked,) = cursor.fetchone()
        if not locked:
            raise ConflictError(
                "A performance check is already running. Try again in a minute.", code="BUSY"
            )
        return self

    def __exit__(self, *exc):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [_CHECK_LOCK])
        return False


def run_index_check(*, trigger: str, actor=None, request=None) -> PerformanceCheck:
    started_at = timezone.now()
    with _OneAtATime():
        results, _ = plans.run_index_check()
        rows = dataset()
    return record(
        kind=PerformanceCheck.Kind.INDEXES,
        trigger=trigger,
        started_at=started_at,
        results=results,
        rows=rows,
        actor=actor,
        request=request,
    )


def run_response_times(
    *, trigger: str, samples: int = timings.DEFAULT_SAMPLES, actor=None
) -> PerformanceCheck:
    _require_local("Measuring response times from HIMS")
    started_at = timezone.now()
    with _OneAtATime():
        results = timings.measure(samples=samples)
        rows = dataset()
    return record(
        kind=PerformanceCheck.Kind.RESPONSE_TIMES,
        trigger=trigger,
        started_at=started_at,
        results=results,
        rows=rows,
        actor=actor,
    )


def performance_status() -> dict:
    latest = PerformanceCheck.objects.order_by("-finished_at")

    def last(kind, **extra):
        return latest.filter(kind=kind, **extra).first()

    return {
        "can_measure_here": can_run_here(),
        "page_target_ms": timings.PAGE_MS,
        "search_target_ms": timings.SEARCH_MS,
        "last_index_check": last(PerformanceCheck.Kind.INDEXES),
        "last_response_times": last(PerformanceCheck.Kind.RESPONSE_TIMES),
        "last_volume_index_check": last(
            PerformanceCheck.Kind.INDEXES, trigger=PerformanceCheck.Trigger.VOLUME
        ),
        "last_volume_response_times": last(
            PerformanceCheck.Kind.RESPONSE_TIMES, trigger=PerformanceCheck.Trigger.VOLUME
        ),
    }


# --- The volume check: a throw-away copy with production-like synthetic records -------------


def _owner_database() -> dict:
    from apps.recovery.pg_tools import database_settings

    return database_settings()


def _url(database: dict, name: str) -> str:
    user = quote(database.get("USER") or "", safe="")
    password = quote(database.get("PASSWORD") or "", safe="")
    credentials = f"{user}:{password}@" if password else (f"{user}@" if user else "")
    host = database.get("HOST") or "localhost"
    port = database.get("PORT") or 5432
    return f"postgres://{credentials}{host}:{port}/{name}"


def _recreate(database: dict, *, drop_only: bool = False) -> None:
    from apps.recovery.pg_tools import connect

    try:
        with connect(database) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{VOLUME_DATABASE}" WITH (FORCE)')
            if not drop_only:
                admin.execute(f'CREATE DATABASE "{VOLUME_DATABASE}" TEMPLATE template0')
    except psycopg.Error as exc:
        raise PerformanceError(
            f"The throw-away database {VOLUME_DATABASE} could not be created or removed (the "
            f"database user needs permission to create databases): {scrub(str(exc))[:200]}"
        ) from exc


def _vacuum(database: dict) -> None:
    from apps.recovery.pg_tools import connect

    try:
        with connect(database, name=VOLUME_DATABASE) as copy:
            copy.execute("VACUUM (ANALYZE)")
    except psycopg.Error as exc:
        raise PerformanceError(
            f"The throw-away copy could not be tidied: {scrub(str(exc))[:200]}"
        ) from exc


def _child_env(database: dict, folder: Path) -> dict:
    env = dict(os.environ)
    env.update(
        DATABASE_URL=_url(database, VOLUME_DATABASE),
        HIMS_MIGRATION_DATABASE_URL="",  # the copy has one user: the owner
        HIMS_MEDIA_ROOT=str(folder / "media"),
        HIMS_TRACING_EXPORTER="none",
        PYTHONIOENCODING="utf-8",
    )
    return env


def _manage(env: dict, *args: str, say) -> None:
    command = [sys.executable, str(Path(settings.BASE_DIR) / "manage.py"), *args]
    result = subprocess.run(  # noqa: S603 - our own manage.py with fixed arguments
        command,
        cwd=settings.BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=3600,
        check=False,
    )
    for line in result.stdout.splitlines():
        say(f"  {line}")
    if result.returncode != 0:
        tail = scrub(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "")
        raise PerformanceError(f"'{args[0]}' failed on the throw-away copy: {tail[:300]}")


def run_volume_check(
    *,
    scale: float = 1.0,
    samples: int = timings.DEFAULT_SAMPLES,
    keep: bool = False,
    actor=None,
    say=print,
) -> list[PerformanceCheck]:
    """Build the throw-away copy, fill it, check it, record the results here, remove it."""
    from apps.organizations.models import Organization

    _require_local("The volume check")
    live = connection.settings_dict["NAME"]
    if live == VOLUME_DATABASE:
        raise PerformanceError("Run the volume check from a hospital's settings, not the copy's.")
    organization = Organization.objects.first()
    if organization is None:
        raise PerformanceError("Provision the organization first (provision_organization).")
    database = _owner_database()
    folder = Path(tempfile.mkdtemp(prefix="hims-volume-check-"))
    env = _child_env(database, folder)
    say(f"Creating the throw-away database {VOLUME_DATABASE}...")
    _recreate(database)
    recorded = []
    try:
        _manage(env, "migrate", "--no-input", "-v", "0", say=say)
        _manage(
            env,
            "provision_organization",
            f"--legal-name={organization.legal_name} (volume copy)",
            f"--display-name={organization.display_name} (volume copy)",
            f"--country={organization.country}",
            f"--timezone={organization.default_timezone}",
            f"--currency={organization.default_currency}",
            "--admin-email=volume.admin@synthetic.test",
            "--admin-name=Synthetic Volume Admin",
            say=say,
        )
        _manage(env, "seed_volume_data", f"--scale={scale}", say=say)
        # A hospital's audit log is sealed every minute (HIMS-SEC-010), so the copy's is too.
        say("Sealing the copy's audit log, as the every-minute job does in a hospital...")
        _manage(env, "seal_audit_log", say=say)
        # In a hospital PostgreSQL's autovacuum keeps tables tidy in the background; the copy was
        # filled in minutes, so it is done once here before measuring.
        say("Tidying the copy's tables, as PostgreSQL's autovacuum does in a hospital...")
        _vacuum(database)
        outputs = {}
        for kind, command, extra in (
            (PerformanceCheck.Kind.INDEXES, "check_query_plans", []),
            (
                PerformanceCheck.Kind.RESPONSE_TIMES,
                "measure_response_times",
                [f"--samples={samples}"],
            ),
        ):
            target = folder / f"{kind}.json"
            say(f"Running {command} on the copy...")
            _manage(env, command, f"--json={target}", "--no-fail", *extra, say=say)
            outputs[kind] = json.loads(target.read_text(encoding="utf-8"))
        for kind, output in outputs.items():
            recorded.append(
                record(
                    kind=kind,
                    trigger=PerformanceCheck.Trigger.VOLUME,
                    started_at=output["started_at"],
                    results=output["results"],
                    rows=output["dataset"],
                    database=f"{VOLUME_DATABASE} (throw-away copy, synthetic records)",
                    actor=actor,
                )
            )
    finally:
        if keep:
            say(f"Kept {VOLUME_DATABASE} for a closer look (remove it with --remove-copy).")
        else:
            say(f"Removing {VOLUME_DATABASE}...")
            _recreate(database, drop_only=True)
        shutil.rmtree(folder, ignore_errors=True)
    return recorded


def remove_volume_copy() -> None:
    _require_local("The volume check")
    _recreate(_owner_database(), drop_only=True)
