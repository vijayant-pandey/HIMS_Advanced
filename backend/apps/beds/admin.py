from django import forms
from django.contrib import admin, messages

from apps.facilities.admin import RoomAdmin, _LocationAdmin
from common.admin.options import HimsInline
from common.exceptions import DomainError

from .models import Bed
from .services import change_bed_status

STATUS_CHOICES = [("", "— keep current status —")] + [
    (status.value, status.label) for status in Bed.Status if status in Bed.OPERATIONAL_STATES
]


class BedInline(HimsInline):
    model = Bed
    fields = ("code", "bed_type", "status", "is_active")
    readonly_fields = ("status",)


# Beds live in this app; show them on the room page next to the other location levels.
RoomAdmin.inlines = [*RoomAdmin.inlines, BedInline]


class BedForm(forms.ModelForm):
    """Status is never edited as a field; these two inputs go through change_bed_status, which
    applies the same rules, audit and event as the app (reason required, ADT states refused)."""

    new_status = forms.ChoiceField(choices=STATUS_CHOICES, required=False, label="Change status to")
    new_status_reason = forms.CharField(
        required=False,
        max_length=255,
        label="Reason",
        help_text="Required unless the bed becomes available, e.g. 'Broken side rail'. "
        "No patient details.",
    )

    class Meta:
        model = Bed
        fields = ("room", "code", "bed_type", "is_active")

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("new_status")
        if status and self.instance.pk and self.instance.status in Bed.ADT_STATES:
            raise forms.ValidationError(
                "This bed's status is managed by admissions, transfers, discharges and cleaning."
            )
        if status and status != Bed.Status.AVAILABLE and not cleaned.get("new_status_reason"):
            self.add_error("new_status_reason", "Say why the bed is unavailable.")
        return cleaned


@admin.register(Bed)
class BedAdmin(_LocationAdmin):
    form = BedForm
    parent_field = "room"
    list_display = ("code", "ward", "room", "bed_type", "status", "status_reason", "is_active")
    list_filter = ("status", "bed_type", "is_active", "facility")
    search_fields = ("code", "ward__code", "room__code")
    fieldsets = (
        (None, {"fields": ("room", "code", "bed_type", "is_active")}),
        (
            "Status",
            {
                "fields": (
                    "status",
                    "status_reason",
                    "status_changed_at",
                    "new_status",
                    "new_status_reason",
                )
            },
        ),
        ("Record", {"fields": ("version", "created_at", "updated_at")}),
    )
    readonly_fields = ("status", "status_reason", "status_changed_at")
    actions = ["mark_available", "mark_out_of_service"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        status = form.cleaned_data.get("new_status")
        if status:
            try:
                change_bed_status(
                    actor=request.user,
                    bed_id=obj.pk,
                    version=obj.version,
                    status=status,
                    reason=form.cleaned_data.get("new_status_reason", ""),
                    request=request,
                )
            except DomainError as exc:
                self.message_user(request, f"Status not changed: {exc}", messages.WARNING)

    def _change_status(self, request, queryset, status, reason):
        changed = 0
        for bed in queryset:
            try:
                change_bed_status(
                    actor=request.user,
                    bed_id=bed.pk,
                    version=bed.version,
                    status=status,
                    reason=reason,
                    request=request,
                )
                changed += 1
            except DomainError as exc:
                self.message_user(request, f"{bed}: {exc}", messages.WARNING)
        if changed:
            self.message_user(request, f"{changed} bed(s) updated.", messages.SUCCESS)

    @admin.action(description="Mark selected beds available")
    def mark_available(self, request, queryset):
        self._change_status(request, queryset, Bed.Status.AVAILABLE, "")

    @admin.action(description="Mark selected beds out of service")
    def mark_out_of_service(self, request, queryset):
        self._change_status(request, queryset, Bed.Status.OUT_OF_SERVICE, "Set from admin console")
