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
def handle_event(self, event_id: str) -> None:
    try:
        process_event(event_id)
    except Exception as exc:
        logger.warning(
            "Outbox handler failed; retrying",
            extra={"event_id": event_id, "error": type(exc).__name__},
        )
        raise self.retry(exc=exc) from exc
