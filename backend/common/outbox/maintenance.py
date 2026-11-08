"""Looking after the outbox (spec 14.3 "monitor queue depth, task age, retries and
exhausted-retry cases"; HIMS-PLAT-014). Runbook: docs/runbooks/outbox-and-background-jobs.md.

* **Clean-up** (daily): published and dismissed events older than ``HIMS_OUTBOX_RETENTION_DAYS``
  are deleted in small batches, with the duplicate-check markers of events that can no longer
  come back. Waiting and failed events are never deleted automatically: a person decides.
* **Health**: how many events wait, how old the oldest is, how many are being retried, how many
  failed for good. Checked every 15 minutes; a warning line is logged for monitoring when
  something needs a look.
* **Decisions on a failed event**: send it again (after the cause is fixed) or dismiss it (it can
  never succeed, e.g. what it was about no longer exists). Both need a reason and are audited.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Min, Q
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction, record_audit_event
from common.exceptions import ConflictError

from .models import OutboxEvent, ProcessedEvent

logger = logging.getLogger(__name__)

Status = OutboxEvent.Status
DELETE_BATCH = 2000
# Events whose handlers may still run: their duplicate-check markers must stay.
_MAY_RUN_AGAIN = (Status.PENDING, Status.DEAD)


def _delete_in_batches(queryset) -> int:
    """Delete in small transactions, so the tables are never locked for long."""
    deleted = 0
    model = queryset.model
    while True:
        ids = list(queryset.values_list("pk", flat=True)[:DELETE_BATCH])
        if not ids:
            return deleted
        with transaction.atomic():
            count, _ = model.objects.filter(pk__in=ids).delete()
        deleted += count


def purge_old_events(*, now=None, actor=None, request=None) -> dict:
    """Delete published and dismissed events past the retention period, and markers of events
    that can no longer run again. Returns what was deleted (also written to the audit log)."""
    now = now or timezone.now()
    days = settings.HIMS_OUTBOX_RETENTION_DAYS
    cutoff = now - timedelta(days=days)
    events = _delete_in_batches(
        OutboxEvent.objects.filter(
            Q(status=Status.PUBLISHED, published_at__lt=cutoff)
            | Q(status=Status.DISMISSED, resolved_at__lt=cutoff)
        ).order_by("pk")
    )
    still_needed = OutboxEvent.objects.filter(status__in=_MAY_RUN_AGAIN).values("pk")
    markers = _delete_in_batches(
        ProcessedEvent.objects.filter(processed_at__lt=cutoff)
        .exclude(event_id__in=still_needed)
        .order_by("pk")
    )
    result = {"events_deleted": events, "markers_deleted": markers, "retention_days": days}
    record_audit_event(
        action=AuditAction.OUTBOX_CLEANED_UP,
        resource_type="outbox",
        actor=actor,
        request=request,
        metadata={**result, "older_than": cutoff.isoformat()},
    )
    logger.info("outbox_cleaned_up", extra=result)
    return result


def _last_cleanup() -> dict | None:
    row = (
        AuditEvent.objects.filter(action=AuditAction.OUTBOX_CLEANED_UP)
        .order_by("-occurred_at")
        .values("occurred_at", "metadata")
        .first()
    )
    if row is None:
        return None
    return {
        "at": row["occurred_at"],
        "events_deleted": row["metadata"].get("events_deleted", 0),
        "markers_deleted": row["metadata"].get("markers_deleted", 0),
    }


def outbox_health(*, now=None) -> dict:
    """Where the outbox stands now, and what needs a look."""
    now = now or timezone.now()
    waiting = OutboxEvent.objects.filter(status=Status.PENDING)
    oldest = waiting.aggregate(oldest=Min("occurred_at"))["oldest"]
    oldest_minutes = int((now - oldest).total_seconds() // 60) if oldest else 0
    stuck_after = settings.HIMS_OUTBOX_STUCK_MINUTES
    failed = OutboxEvent.objects.filter(status=Status.DEAD).count()
    stuck = waiting.filter(occurred_at__lt=now - timedelta(minutes=stuck_after)).count()
    attention = []
    if failed:
        attention.append(f"{failed} event(s) failed after every retry and need a decision")
    if stuck:
        attention.append(
            f"{stuck} event(s) have been waiting more than {stuck_after} minutes "
            f"(oldest: {oldest_minutes} minutes)"
        )
    return {
        "waiting": waiting.count(),
        "oldest_waiting_minutes": oldest_minutes,
        "retrying": waiting.filter(attempts__gt=0).count(),
        "stuck": stuck,
        "failed": failed,
        "dismissed": OutboxEvent.objects.filter(status=Status.DISMISSED).count(),
        "published_last_24h": OutboxEvent.objects.filter(
            status=Status.PUBLISHED, published_at__gte=now - timedelta(hours=24)
        ).count(),
        "stuck_after_minutes": stuck_after,
        "retention_days": settings.HIMS_OUTBOX_RETENTION_DAYS,
        "max_attempts": settings.HIMS_OUTBOX_MAX_ATTEMPTS,
        "last_cleanup": _last_cleanup(),
        "attention": attention,
    }


def warn_if_attention_needed() -> list[str]:
    """Periodic check: a warning line for monitoring (alarms come with hosting, HIMS-OPS-004)."""
    attention = outbox_health()["attention"]
    if attention:
        logger.warning("outbox_attention_needed", extra={"problems": attention})
    return attention


def _decide(*, actor, event_id, reason: str, request, allowed: tuple, apply, action: str):
    reason = (reason or "").strip()
    if not reason:
        raise ConflictError("Give a reason, so the decision can be understood later.")
    with transaction.atomic():
        event = OutboxEvent.objects.select_for_update().get(pk=event_id)
        if event.status not in allowed:
            raise ConflictError(
                f"This event is {event.get_status_display().lower()}; nothing to decide."
            )
        before = event.status
        apply(event)
        event.resolved_at = timezone.now()
        event.resolved_by_id = getattr(actor, "pk", None)
        event.resolution_note = reason[:300]
        event.save()
        record_audit_event(
            action=action,
            resource_type="outbox_event",
            resource_id=event.pk,
            actor=actor,
            request=request,
            reason=reason[:300],
            changes={"status": {"before": before, "after": event.status}},
            metadata={"event_type": event.event_type, "attempts_before": event.attempts},
        )
    return event


def send_again(*, actor, event_id, reason: str, request=None) -> OutboxEvent:
    """A failed (or stuck) event goes back to the queue with a fresh set of retries."""

    def apply(event):
        event.status = Status.PENDING
        event.attempts = 0
        event.available_at = timezone.now()

    return _decide(
        actor=actor,
        event_id=event_id,
        reason=reason,
        request=request,
        allowed=(Status.DEAD, Status.PENDING),
        apply=apply,
        action=AuditAction.OUTBOX_EVENT_SENT_AGAIN,
    )


def dismiss(*, actor, event_id, reason: str, request=None) -> OutboxEvent:
    """A failed event that can never succeed is closed; it is never retried."""

    def apply(event):
        event.status = Status.DISMISSED

    return _decide(
        actor=actor,
        event_id=event_id,
        reason=reason,
        request=request,
        allowed=(Status.DEAD,),
        apply=apply,
        action=AuditAction.OUTBOX_EVENT_DISMISSED,
    )
