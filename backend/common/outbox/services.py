from django.conf import settings
from django.db import transaction

from common.request_context import get_request_id

from .models import OutboxEvent


class OutboxUsageError(RuntimeError):
    pass


def publish_event(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id,
    payload: dict,
    facility_id=None,
    causation_id: str = "",
    event_version: int = 1,
) -> OutboxEvent:
    """Record a domain event in the caller's transaction.

    Keep payloads minimal (identifiers, not clinical content). Must be called inside the
    ``transaction.atomic`` block that changes the aggregate; otherwise the dual-write problem
    the outbox exists to prevent comes back (ADR-005).
    """
    if not transaction.get_connection().in_atomic_block:
        raise OutboxUsageError("publish_event must run inside the aggregate's transaction.")
    event = OutboxEvent.objects.create(
        event_type=event_type,
        event_version=event_version,
        customer_id=settings.HIMS_DEPLOYMENT_ID,
        facility_id=facility_id,
        aggregate_type=aggregate_type,
        aggregate_id=str(aggregate_id),
        correlation_id=get_request_id() or "",
        causation_id=causation_id,
        payload=payload,
    )
    if settings.HIMS_OUTBOX_DISPATCH_INLINE:
        from .dispatcher import dispatch_inline

        transaction.on_commit(lambda: dispatch_inline(event.pk))
    return event
