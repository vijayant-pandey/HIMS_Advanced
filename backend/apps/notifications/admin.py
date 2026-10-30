from django.contrib import admin, messages

from apps.access_control.catalog import P
from apps.access_control.selectors import has_permission
from common.admin.options import ReadOnlyModelAdmin
from common.exceptions import DomainError

from .models import Notification
from .services import retry_now


@admin.register(Notification)
class NotificationAdmin(ReadOnlyModelAdmin):
    """Every email and SMS HIMS sent (HIMS-NOTIF-001). Read only: sign-in links and secrets
    are hidden in the stored copy; failed messages can be sent again."""

    list_display = ("created_at", "channel", "template", "to", "subject", "status", "attempts")
    list_filter = ("channel", "status", "category")
    search_fields = ("subject", "template", "recipients")
    date_hierarchy = "created_at"
    actions = ["send_again"]
    fields = (
        "created_at",
        "channel",
        "category",
        "template",
        "recipients",
        "subject",
        "body",
        "status",
        "attempts",
        "last_error",
        "next_attempt_at",
        "sent_at",
        "skip_reason",
        "related_type",
        "related_id",
    )
    readonly_fields = fields

    @admin.display(description="To")
    def to(self, obj):
        return ", ".join(obj.recipients)

    def has_view_permission(self, request, obj=None):
        return has_permission(request.user, P.NOTIFICATIONS_VIEW)

    def has_module_permission(self, request):
        return has_permission(request.user, P.NOTIFICATIONS_VIEW)

    @admin.action(description="Send the selected failed messages again")
    def send_again(self, request, queryset):
        if not has_permission(request.user, P.NOTIFICATIONS_MANAGE):
            self.message_user(request, "You may not send messages again.", messages.ERROR)
            return
        for notification in queryset:
            try:
                result = retry_now(
                    actor=request.user, notification_id=notification.pk, request=request
                )
                self.message_user(request, f"{notification}: {result.get_status_display()}.")
            except DomainError as exc:
                self.message_user(request, f"{notification}: {exc.detail}", messages.ERROR)
