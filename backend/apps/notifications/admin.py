from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.core.validators import validate_email
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from apps.access_control.catalog import P
from apps.access_control.selectors import has_permission
from common.admin.options import ConfirmIdentityAdminMixin, HimsModelAdmin, ReadOnlyModelAdmin
from common.exceptions import DomainError

from .message_catalog import BY_KEY
from .message_templates import (
    check_wording,
    ensure_templates,
    preview,
    reset_template,
    to_store,
)
from .models import MessageTemplate, Notification
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


class MessageTemplateForm(forms.ModelForm):
    """Leave both boxes empty to use the standard wording. Same checks as the Message wording
    page: only this message's placeholders, and the ones it cannot do without."""

    class Meta:
        model = MessageTemplate
        fields = ("subject", "body")
        widgets = {"body": forms.Textarea(attrs={"rows": 14, "cols": 90})}

    def clean(self):
        cleaned = super().clean()
        spec = BY_KEY.get(self.instance.key)
        if spec is None or "subject" in self.errors or "body" in self.errors:
            return cleaned
        subject = cleaned.get("subject") or spec.subject
        body = cleaned.get("body") or spec.body
        for field, message in check_wording(spec, subject, body).items():
            self.add_error(field, message)
        return cleaned


@admin.register(MessageTemplate)
class MessageTemplateAdmin(ConfirmIdentityAdminMixin, HimsModelAdmin):
    """The wording of every message HIMS sends (HIMS-NOTIF-003). There is one row per message, so
    none can be added; saving needs a recent "confirm it's you", as in the app, because wording
    reaches everyone, including sign-in links. Changes are audited, before and after."""

    form = MessageTemplateForm
    list_display = ("message", "key", "customised", "updated_at", "updated_by")
    search_fields = ("key", "subject", "body")
    actions = ["use_standard_wording"]
    fields = (
        "key",
        "message",
        "when",
        "placeholders",
        "subject",
        "body",
        "standard_wording",
        "sample",
        "updated_by",
        "version",
        "updated_at",
    )
    readonly_fields = (
        "key",
        "message",
        "when",
        "placeholders",
        "standard_wording",
        "sample",
        "updated_by",
    )

    def has_add_permission(self, request, *args):
        return False

    def changelist_view(self, request, extra_context=None):
        ensure_templates()
        return super().changelist_view(request, extra_context)

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        spec = BY_KEY.get(obj.key)
        if spec is not None:
            obj.subject, obj.body = to_store(spec, obj.subject, obj.body)
        super().save_model(request, obj, form, change)

    @admin.display(description="Message")
    def message(self, obj):
        spec = BY_KEY.get(obj.key)
        return spec.name if spec else "(no longer used)"

    @admin.display(description="Sent when")
    def when(self, obj):
        spec = BY_KEY.get(obj.key)
        return spec.when if spec else "-"

    @admin.display(description="Customised", boolean=True)
    def customised(self, obj):
        return bool(obj.subject or obj.body)

    @admin.display(description="Placeholders you can use")
    def placeholders(self, obj):
        spec = BY_KEY.get(obj.key)
        if spec is None:
            return "-"
        return format_html_join(
            mark_safe("<br>"),
            "{{{{{}}}}}: {}{}",
            (
                (v.name, v.description, " (must stay)" if v.name in spec.required else "")
                for v in spec.variables
            ),
        )

    @admin.display(description="Standard wording")
    def standard_wording(self, obj):
        spec = BY_KEY.get(obj.key)
        if spec is None:
            return "-"
        return format_html("<pre>Subject: {}\n\n{}</pre>", spec.subject, spec.body)

    @admin.display(description="How it reads now (made-up values)")
    def sample(self, obj):
        spec = BY_KEY.get(obj.key)
        if spec is None:
            return "-"
        subject, body = preview(spec, obj.subject or spec.subject, obj.body or spec.body)
        return format_html("<pre>Subject: {}\n\n{}</pre>", subject, body)

    @admin.action(description="Go back to the standard wording")
    def use_standard_wording(self, request, queryset):
        for template in queryset:
            reset_template(
                actor=request.user,
                template_id=template.pk,
                version=template.version,
                request=request,
            )
        self.message_user(request, f"{queryset.count()} message(s) use the standard wording.")
