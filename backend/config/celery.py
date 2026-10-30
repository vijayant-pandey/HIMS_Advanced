"""Celery application (spec 14).

Reliability rules applied here: late acknowledgement, one prefetched task per worker process,
JSON-only payloads, bounded time limits and queue names isolated per customer deployment.
Tasks must still be idempotent: a task may execute more than once (spec 14.3).
"""

import os
from datetime import timedelta

from celery import Celery, signals

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("hims")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,  # durable state lives in PostgreSQL, not the result backend
    task_time_limit=300,
    task_soft_time_limit=240,
    broker_connection_retry_on_startup=True,
    enable_utc=True,
)
app.autodiscover_tasks()


@app.on_after_finalize.connect
def _configure_queues_and_schedule(sender, **kwargs):
    from django.conf import settings

    prefix = settings.HIMS_CELERY_QUEUE_PREFIX
    sender.conf.task_routes = {
        "outbox.*": {"queue": f"{prefix}.outbox"},
        "integrations.*": {"queue": f"{prefix}.integrations"},
        "notifications.*": {"queue": f"{prefix}.notifications"},
        "reports.*": {"queue": f"{prefix}.reports"},
    }
    sender.conf.beat_schedule = {
        "outbox-dispatch": {
            "task": "outbox.dispatch_pending",
            "schedule": timedelta(seconds=5),
            "options": {"expires": 5},
        },
        "idempotency-purge": {
            "task": "platform.purge_expired_idempotency_records",
            "schedule": timedelta(hours=1),
        },
        "expired-sessions-cleanup": {
            "task": "platform.clear_expired_sessions",
            "schedule": timedelta(hours=24),
        },
        "credential-expiry-alerts": {
            "task": "notifications.credential_expiry_alerts",
            "schedule": timedelta(hours=24),
        },
        "access-review-reminders": {
            "task": "notifications.access_review_reminders",
            "schedule": timedelta(hours=24),
        },
        "notification-retries": {
            "task": "notifications.retry_failed",
            "schedule": timedelta(minutes=5),
            "options": {"expires": 300},
        },
        "audit-seal-events": {
            "task": "platform.audit_seal_events",
            "schedule": timedelta(minutes=1),
            "options": {"expires": 60},
        },
        "audit-integrity-check": {
            "task": "platform.audit_integrity_check",
            "schedule": timedelta(hours=24),
        },
    }


# --- Correlation ID propagation from API requests into tasks (spec 29.1) -----------------
_REQUEST_ID_HEADER = "hims_request_id"


@signals.before_task_publish.connect
def _attach_request_id(headers=None, **kwargs):
    from common.request_context import get_request_id

    request_id = get_request_id()
    if headers is not None and request_id:
        headers[_REQUEST_ID_HEADER] = request_id


@signals.worker_process_init.connect
def _start_tracing(**kwargs):
    # In each worker process after it starts (span exporters do not survive a fork).
    from common.tracing import configure_tracing

    configure_tracing("hims-worker", django=False)


@signals.task_prerun.connect
def _restore_request_id(task=None, **kwargs):
    from common.request_context import new_request_id, set_request_id

    request_id = getattr(task.request, _REQUEST_ID_HEADER, None) if task else None
    set_request_id(request_id or new_request_id())
