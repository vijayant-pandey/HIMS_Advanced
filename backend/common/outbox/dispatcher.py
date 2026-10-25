"""Outbox dispatcher and consumer runtime (ADR-012).

The dispatcher claims pending rows with ``SELECT ... FOR UPDATE SKIP LOCKED`` so several
dispatcher processes can run safely, publishes each to the Celery broker and marks it
published. Publication is at-least-once: a crash between broker publish and commit republishes
the event, and consumers deduplicate by ``event_id``. Ordering across events is not
guaranteed; handlers must tolerate reordering.
"""

import logging
import random
from collections.abc import Callable
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import OutboxEvent, ProcessedEvent
from .registry import handlers_for

logger = logging.getLogger(__name__)

MAX_BACKOFF_SECONDS = 15 * 60


def _backoff(attempts: int) -> timedelta:
    base = min(MAX_BACKOFF_SECONDS, 2**attempts)
    return timedelta(seconds=base + random.uniform(0, base / 2))  # noqa: S311 (jitter)


def publish_to_broker(event: OutboxEvent) -> None:
    from config.celery import app

    app.send_task(
        "outbox.handle_event",
        args=[str(event.id)],
        queue=f"{settings.HIMS_CELERY_QUEUE_PREFIX}.outbox",
        headers={"hims_request_id": event.correlation_id},
    )


def dispatch_pending(
    *, batch_size: int | None = None, publish: Callable[[OutboxEvent], None] = publish_to_broker
) -> int:
    batch_size = batch_size or settings.HIMS_OUTBOX_BATCH_SIZE
    now = timezone.now()
    with transaction.atomic():
        events = list(
            OutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(status=OutboxEvent.Status.PENDING, available_at__lte=now)
            .order_by("occurred_at")[:batch_size]
        )
        for event in events:
            try:
                publish(event)
            except Exception as exc:
                event.attempts += 1
                event.last_error = type(exc).__name__[:500]
                if event.attempts >= settings.HIMS_OUTBOX_MAX_ATTEMPTS:
                    event.status = OutboxEvent.Status.DEAD
                    logger.error(
                        "Outbox event exhausted publish retries",
                        extra={"event_id": str(event.id), "event_type": event.event_type},
                    )
                else:
                    event.available_at = now + _backoff(event.attempts)
            else:
                event.status = OutboxEvent.Status.PUBLISHED
                event.published_at = now
            event.save(
                update_fields=["status", "attempts", "available_at", "published_at", "last_error"]
            )
    return len(events)


def process_event(event_id) -> None:
    """Run every registered handler for an event, each at most once. Raises on failure so the
    Celery task retries; already-completed handlers are skipped on retry."""
    try:
        event = OutboxEvent.objects.get(pk=event_id)
    except OutboxEvent.DoesNotExist:
        logger.warning("Outbox event not found", extra={"event_id": str(event_id)})
        return

    for name, handler in handlers_for(event.event_type):
        with transaction.atomic():
            try:
                with transaction.atomic():
                    ProcessedEvent.objects.create(handler=name, event_id=event.id)
            except IntegrityError:
                continue  # already processed by this handler
            handler(event)
