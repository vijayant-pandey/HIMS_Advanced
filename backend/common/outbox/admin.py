from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.template.response import TemplateResponse

from apps.access_control.catalog import P
from apps.access_control.selectors import has_permission
from common.admin.options import LargeTableAdminMixin, ReadOnlyModelAdmin
from common.exceptions import ConflictError

from .maintenance import dismiss, outbox_health, send_again
from .models import OutboxEvent, ProcessedEvent, ScheduledJob


@admin.register(OutboxEvent)
class OutboxEventAdmin(LargeTableAdminMixin, ReadOnlyModelAdmin):
    """The same health summary and decisions as the Background jobs page (HIMS-PLAT-014)."""

    change_list_template = "admin/outbox/outboxevent/change_list.html"
    list_display = (
        "occurred_at",
        "event_type",
        "status",
        "attempts",
        "published_at",
        "last_error",
        "resolution_note",
    )
    list_filter = ("status", ("occurred_at", admin.DateFieldListFilter))
    search_fields = ("id", "event_type", "aggregate_id", "correlation_id")
    actions = ["requeue", "dismiss_selected"]

    def changelist_view(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), "health": outbox_health()}
        return super().changelist_view(request, extra_context)

    def _may_decide(self, request) -> bool:
        if has_permission(request.user, P.JOBS_MANAGE):
            return True
        self.message_user(request, "You may not decide on background events.", messages.ERROR)
        return False

    @admin.action(description="Send selected failed/waiting events again (audited)")
    def requeue(self, request, queryset):
        """Same decision as "Send again" on the Background jobs page (HIMS-PLAT-014)."""
        if not self._may_decide(request):
            return
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

    @admin.action(description="Dismiss selected failed events (asks for a reason; audited)")
    def dismiss_selected(self, request, queryset):
        """Same decision as "Dismiss" on the Background jobs page: a failed event that can never
        succeed is closed with a typed reason and never retried."""
        if not self._may_decide(request):
            return None
        failed = queryset.filter(status=OutboxEvent.Status.DEAD)
        reason = (request.POST.get("reason") or "").strip()
        if "apply" not in request.POST or not reason:
            if "apply" in request.POST:
                self.message_user(request, "Give a reason for dismissing.", messages.ERROR)
            context = {
                **self.admin_site.each_context(request),
                "title": "Dismiss failed events",
                "events": failed,
                "selected": queryset.values_list("pk", flat=True),
                "skipped": queryset.count() - failed.count(),
                "opts": self.model._meta,
                "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            }
            return TemplateResponse(request, "admin/outbox/outboxevent/dismiss.html", context)
        dismissed = 0
        for event in failed:
            try:
                dismiss(actor=request.user, event_id=event.pk, reason=reason, request=request)
            except ConflictError as exc:
                self.message_user(request, f"{event.event_type}: {exc.detail}", messages.ERROR)
                continue
            dismissed += 1
        self.message_user(request, f"Dismissed {dismissed} event(s).")
        return None


@admin.register(ProcessedEvent)
class ProcessedEventAdmin(ReadOnlyModelAdmin):
    list_display = ("processed_at", "handler", "event_id")
    search_fields = ("event_id", "handler")


@admin.register(ScheduledJob)
class ScheduledJobAdmin(ReadOnlyModelAdmin):
    """The last run of each scheduled job started by run_scheduled_jobs (HIMS-OPS-023), the same
    as the Background jobs page. Read-only: runs are started by the host's timer, not from here."""

    list_display = (
        "name",
        "job",
        "every_seconds",
        "last_started_at",
        "last_outcome",
        "last_duration_ms",
        "runs",
        "failures",
    )
    list_filter = ("last_outcome",)
    search_fields = ("name", "task")

    @admin.display(description="What it does")
    def job(self, obj):
        from config.schedule import LABELS

        return LABELS.get(obj.name, obj.name)
