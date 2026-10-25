from django.contrib import admin
from django.utils import timezone

from apps.audit.services import record_audit_event
from common.admin.options import ReadOnlyModelAdmin

from .models import OutboxEvent, ProcessedEvent


@admin.register(OutboxEvent)
class OutboxEventAdmin(ReadOnlyModelAdmin):
    list_display = ("occurred_at", "event_type", "status", "attempts", "published_at", "last_error")
    list_filter = ("status", "event_type")
    search_fields = ("id", "aggregate_id", "correlation_id")
    date_hierarchy = "occurred_at"
    actions = ["requeue"]

    @admin.action(description="Requeue selected dead/pending events for dispatch")
    def requeue(self, request, queryset):
        events = queryset.exclude(status=OutboxEvent.Status.PUBLISHED)
        ids = [str(pk) for pk in events.values_list("pk", flat=True)]
        events.update(status=OutboxEvent.Status.PENDING, attempts=0, available_at=timezone.now())
        record_audit_event(
            action="admin.outboxevent.requeued",
            resource_type="outbox_event",
            request=request,
            metadata={"via": "admin-console", "event_ids": ids},
        )
        self.message_user(request, f"Requeued {len(ids)} event(s).")


@admin.register(ProcessedEvent)
class ProcessedEventAdmin(ReadOnlyModelAdmin):
    list_display = ("processed_at", "handler", "event_id")
    search_fields = ("event_id", "handler")
