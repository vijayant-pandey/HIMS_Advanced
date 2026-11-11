"""Scheduled jobs without an always-on scheduler (spec 14; HIMS-OPS-023).

Hosted with Celery beat and a worker, nothing here is used. On a host that can only start a
command on a timer (Northflank's scheduled jobs, GitHub Actions; ADR-034), that command is
``python manage.py run_scheduled_jobs``: every call runs each job of config/schedule.py whose time
has come, once, in this process, and records the outcome in ``scheduled_jobs``.

* Never twice at the same time: a PostgreSQL advisory lock; a second call while one is still
  running does nothing and says so.
* One failing job does not stop the others; its error (filtered like the logs) is kept on its row
  and the command ends with an error so the host shows the run as failed.
* Jobs due more often than the timer (sending background events every 5 seconds, sealing the audit
  log every minute) simply run on every call.
"""

import logging
import time
from datetime import timedelta

from django.db import connection
from django.utils import timezone

from common.log_safety import scrub
from config.schedule import LABELS, SCHEDULE

from .models import ScheduledJob

logger = logging.getLogger(__name__)

_LOCK = 7_406_023
# A timer that fires a moment early still counts as on time.
_EARLY = timedelta(seconds=5)
# A failed job is tried again this soon (or at its normal time, if that comes first).
RETRY_AFTER = timedelta(minutes=5)


class _OneRunAtATime:
    def __enter__(self) -> bool:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [_LOCK])
            (self.locked,) = cursor.fetchone()
        return self.locked

    def __exit__(self, *exc):
        if self.locked:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [_LOCK])
        return False


def _row(name: str, job: dict) -> ScheduledJob:
    row, _ = ScheduledJob.objects.get_or_create(
        name=name,
        defaults={"task": job["task"], "every_seconds": int(job["every"].total_seconds())},
    )
    return row


def is_due(row: ScheduledJob, every: timedelta, now) -> bool:
    if row.last_started_at is None:
        return True
    wait = min(every, RETRY_AFTER) if row.last_outcome == ScheduledJob.Outcome.FAILED else every
    return now - row.last_started_at >= wait - _EARLY


def _tasks():
    """Celery's task list; outside a worker the task modules must be loaded first."""
    from config.celery import app

    app.loader.import_default_modules()
    return app.tasks


def _run(row: ScheduledJob, task_name: str) -> dict:
    started = timezone.now()
    ScheduledJob.objects.filter(pk=row.pk).update(
        last_started_at=started, last_outcome=ScheduledJob.Outcome.RUNNING
    )
    clock = time.monotonic()
    error = ""
    try:
        result = _tasks()[task_name].apply()
        if result.failed():
            error = scrub(f"{type(result.result).__name__}: {result.result}")[:300]
    except Exception as exc:  # a broken job must not stop the others
        error = scrub(f"{type(exc).__name__}: {exc}")[:300]
    duration = int((time.monotonic() - clock) * 1000)
    outcome = ScheduledJob.Outcome.FAILED if error else ScheduledJob.Outcome.OK
    row.refresh_from_db()
    row.last_finished_at = timezone.now()
    row.last_outcome = outcome
    row.last_duration_ms = duration
    row.last_error = error
    row.runs += 1
    row.failures += 1 if error else 0
    row.save()
    if error:
        logger.error("Scheduled job failed", extra={"job": row.name, "error": error})
    return {"job": row.name, "outcome": outcome, "duration_ms": duration, "error": error}


def run_due(*, now=None, only: str | None = None) -> dict:
    """Run every due job once. Returns what ran, or ``busy`` when another run holds the lock."""
    if only is not None and only not in SCHEDULE:
        raise KeyError(only)
    with _OneRunAtATime() as locked:
        if not locked:
            return {"busy": True, "ran": []}
        now = now or timezone.now()
        ran = []
        for name, job in SCHEDULE.items():
            if only is not None and name != only:
                continue
            row = _row(name, job)
            if only is not None or is_due(row, job["every"], now):
                ran.append(_run(row, job["task"]))
        return {"busy": False, "ran": ran}


def board() -> list[dict]:
    """Every scheduled job with its last run, for the Background jobs page and the console."""
    rows = {row.name: row for row in ScheduledJob.objects.all()}
    found = []
    for name, job in SCHEDULE.items():
        row = rows.get(name)
        found.append(
            {
                "name": name,
                "label": LABELS.get(name, name),
                "every_seconds": int(job["every"].total_seconds()),
                "last_started_at": row.last_started_at if row else None,
                "last_finished_at": row.last_finished_at if row else None,
                "last_outcome": row.last_outcome if row else "",
                "last_duration_ms": row.last_duration_ms if row else None,
                "last_error": row.last_error if row else "",
                "runs": row.runs if row else 0,
                "failures": row.failures if row else 0,
            }
        )
    return found
