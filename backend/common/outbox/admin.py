from django.contrib import admin

from common.admin.options import ReadOnlyModelAdmin
from common.exceptions import ConflictError

from .maintenance import send_again
from .models import OutboxEvent, ProcessedEvent


@admin.register(OutboxEvent)
class OutboxEventAdmin(ReadOnlyModelAdmin):
    list_display = (
        "occurred_at",
        "event_type",
        "status",
        "attempts",
        "published_at",
        "last_error",
        "resolution_note",
    )
    list_filter = ("status", "event_type")
    search_fields = ("id", "aggregate_id", "correlation_id")
    date_hierarchy = "occurred_at"
    actions = ["requeue"]

    @admin.action(description="Send selected failed/waiting events again (audited)")
    def requeue(self, request, queryset):
        """Same decision as "Send again" on the Background jobs page (HIMS-PLAT-014). Dismissing
        needs a typed reason, so it is done on that page."""
        sent = 0
        for event in queryset.exclude(status=OutboxEvent.Status.PUBLISHED):
            try:
                send_again(
                    actor=request.user,
                    event_id=event.pk,
                    reason="Sent again from the admin console",
                    request=request,
                )
            except ConflictError:
                continue
            sent += 1
        self.message_user(request, f"Sent {sent} event(s) again.")


@admin.register(ProcessedEvent)
class ProcessedEventAdmin(ReadOnlyModelAdmin):
    list_display = ("processed_at", "handler", "event_id")
    search_fields = ("event_id", "handler")
