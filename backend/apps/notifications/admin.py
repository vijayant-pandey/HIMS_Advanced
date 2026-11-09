from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.core.validators import validate_email
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path

from apps.access_control.catalog import P
from apps.access_control.selectors import has_permission
from common.admin.options import ReadOnlyModelAdmin
from common.exceptions import DomainError

from .models import Notification
from .services import retry_now, send_test


class TestMessageForm(forms.Form):
    channel = forms.ChoiceField(choices=Notification.Channel.choices)
    to = forms.CharField(
        max_length=254, help_text="An email address, or a phone number like +919876543210."
    )

    def clean(self):
        data = super().clean()
        if data.get("channel") == Notification.Channel.EMAIL and data.get("to"):
            try:
                validate_email(data["to"])
            except forms.ValidationError:
                self.add_error("to", "Enter a valid email address.")
        return data


@admin.register(Notification)
class NotificationAdmin(ReadOnlyModelAdmin):
    """Every email and SMS HIMS sent (HIMS-NOTIF-001). Read only: sign-in links and secrets
    are hidden in the stored copy; failed messages can be sent again, and a test message sent
    (same rules and audit as the Messages page)."""

    change_list_template = "admin/notifications/notification/change_list.html"

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

    def changelist_view(self, request, extra_context=None):
        extra_context = {
            **(extra_context or {}),
            "can_manage": has_permission(request.user, P.NOTIFICATIONS_MANAGE),
        }
        return super().changelist_view(request, extra_context)

    def get_urls(self):
        return [
            path(
                "send-test/",
                self.admin_site.admin_view(self.send_test_view),
                name="notifications_notification_send_test",
            ),
            *super().get_urls(),
        ]

    def send_test_view(self, request):
        """Check that email or SMS works: a short message with no personal data (HIMS-NOTIF-001)."""
        if not has_permission(request.user, P.NOTIFICATIONS_MANAGE):
            raise PermissionDenied
        form = TestMessageForm(request.POST if request.method == "POST" else None)
        if request.method == "POST" and form.is_valid():
            notification = send_test(actor=request.user, request=request, **form.cleaned_data)
            self.message_user(
                request, f"Test message: {notification.get_status_display()}.", messages.SUCCESS
            )
            return redirect("admin:notifications_notification_change", notification.pk)
        context = {
            **self.admin_site.each_context(request),
            "title": "Send a test message",
            "form": form,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/notifications/notification/send_test.html", context)

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
