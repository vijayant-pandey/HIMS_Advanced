import logging

from celery import shared_task

from .dispatcher import dispatch_pending as _dispatch_pending
from .dispatcher import process_event

logger = logging.getLogger(__name__)


@shared_task(name="outbox.dispatch_pending", ignore_result=True)
def dispatch_pending() -> int:
    return _dispatch_pending()


@shared_task(
    name="outbox.handle_event",
    bind=True,
    max_retries=10,
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
)
def handle_event(self, event_id: str, deployment: str | None = None) -> None:
    try:
        process_event(event_id, deployment=deployment)
    except Exception as exc:
        logger.warning(
            "Outbox handler failed; retrying",
            extra={"event_id": event_id, "error": type(exc).__name__},
        )
        raise self.retry(exc=exc) from exc


@shared_task(name="platform.outbox_cleanup")
def outbox_cleanup() -> dict:
    """Daily: delete old published and dismissed events (HIMS-PLAT-014)."""
    from .maintenance import purge_old_events

    return purge_old_events()


@shared_task(name="platform.outbox_health_check", ignore_result=True)
def outbox_health_check() -> list[str]:
    """Every 15 minutes: log a warning for monitoring when events are stuck or failed."""
    from .maintenance import warn_if_attention_needed

    return warn_if_attention_needed()
