"""The scheduled jobs (spec 14): one list, read by Celery beat (config/celery.py) and by
``python manage.py run_scheduled_jobs`` (hosts without an always-on scheduler; HIMS-OPS-023), so
the two can never drift apart.

``every`` is how often the job is due; ``expires`` (seconds) drops a beat message that waited too
long in the queue, for jobs where a late run is pointless.
"""

from datetime import timedelta

SCHEDULE: dict[str, dict] = {
    "outbox-dispatch": {
        "task": "outbox.dispatch_pending",
        "every": timedelta(seconds=5),
        "expires": 5,
    },
    "outbox-cleanup": {"task": "platform.outbox_cleanup", "every": timedelta(hours=24)},
    "outbox-health-check": {
        "task": "platform.outbox_health_check",
        "every": timedelta(minutes=15),
        "expires": 900,
    },
    "idempotency-purge": {
        "task": "platform.purge_expired_idempotency_records",
        "every": timedelta(hours=1),
    },
    "expired-sessions-cleanup": {
        "task": "platform.clear_expired_sessions",
        "every": timedelta(hours=24),
    },
    "credential-expiry-alerts": {
        "task": "notifications.credential_expiry_alerts",
        "every": timedelta(hours=24),
    },
    "staffing-gap-alerts": {
        "task": "notifications.staffing_gap_alerts",
        "every": timedelta(hours=24),
    },
    "access-review-reminders": {
        "task": "notifications.access_review_reminders",
        "every": timedelta(hours=24),
    },
    "retention-purge": {"task": "platform.retention_purge", "every": timedelta(hours=24)},
    "incident-deadline-alerts": {
        "task": "notifications.incident_deadline_alerts",
        "every": timedelta(hours=1),
    },
    "notification-retries": {
        "task": "notifications.retry_failed",
        "every": timedelta(minutes=5),
        "expires": 300,
    },
    "audit-seal-events": {
        "task": "platform.audit_seal_events",
        "every": timedelta(minutes=1),
        "expires": 60,
    },
    "audit-integrity-check": {
        "task": "platform.audit_integrity_check",
        "every": timedelta(hours=24),
    },
}

# Plain-language names for the Background jobs page and the console.
LABELS: dict[str, str] = {
    "outbox-dispatch": "Send waiting background events",
    "outbox-cleanup": "Delete old background events",
    "outbox-health-check": "Check background events for problems",
    "idempotency-purge": "Delete expired repeat-request records",
    "expired-sessions-cleanup": "Close expired sign-ins",
    "credential-expiry-alerts": "Licence expiry alerts",
    "staffing-gap-alerts": "Minimum staffing alerts",
    "access-review-reminders": "Access review reminders",
    "retention-purge": "Retention purge",
    "incident-deadline-alerts": "Incident deadline alerts",
    "notification-retries": "Send failed messages again",
    "audit-seal-events": "Seal the audit log",
    "audit-integrity-check": "Check the audit log for tampering",
}


def beat_schedule() -> dict[str, dict]:
    """The same jobs in Celery beat's own format."""
    found = {}
    for name, job in SCHEDULE.items():
        entry = {"task": job["task"], "schedule": job["every"]}
        if "expires" in job:
            entry["options"] = {"expires": job["expires"]}
        found[name] = entry
    return found
