from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html, format_html_join

from apps.organizations.dates import hospital_today
from common.admin.options import HimsModelAdmin
from common.exceptions import DomainError

from . import services
from .models import Equipment, EquipmentServiceRecord

STATUS_CHOICES = [("", "— keep current status —"), *Equipment.Status.choices]


class ServiceDueFilter(admin.SimpleListFilter):
    title = "service or calibration"
    parameter_name = "due"

    def lookups(self, request, model_admin):
        return ((services.OVERDUE, "Overdue"), (services.DUE_SOON, "Due in 30 days"))

    def queryset(self, request, queryset):
        if self.value() in (services.OVERDUE, services.DUE_SOON):
            return services.filter_due(queryset, self.value(), hospital_today())
        return queryset


class EquipmentForm(forms.ModelForm):
    """Status is never edited as a field; these two inputs go through change_status, which applies
    the same rules and audit as the app (a reason unless the equipment is in service)."""

    new_status = forms.ChoiceField(choices=STATUS_CHOICES, required=False, label="Change status to")
    new_status_reason = forms.CharField(
        required=False,
        max_length=255,
        label="Reason",
        help_text="Required unless it goes back into service, e.g. 'Battery fault'. "
        "No patient details.",
    )

    class Meta:
        model = Equipment
        fields = (
            "organization",
            "asset_tag",
            "name",
            "category",
            "notes",
            "facility",
            "department",
            "ward",
            "room",
            "location_note",
            "manufacturer",
            "model_name",
            "serial_number",
            "purchased_on",
            "warranty_until",
            "last_service_on",
            "next_service_due",
            "last_calibrated_on",
            "next_calibration_due",
        )

    def clean_asset_tag(self):
        # Labels are written in capitals, so "vent-1" and "VENT-1" are the same tag.
        return self.cleaned_data["asset_tag"].strip().upper()

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("new_status")
        if (
            status
            and status != Equipment.Status.IN_SERVICE
            and not cleaned.get("new_status_reason", "").strip()
        ):
            self.add_error("new_status_reason", "Say why this equipment cannot be used.")
        return cleaned


@admin.register(Equipment)
class EquipmentAdmin(HimsModelAdmin):
    """The equipment register (HIMS-FAC-009). Same rules and audit as the Equipment page. Visits
    are added under Equipment service records, because the database never lets them change."""

    form = EquipmentForm
    list_display = (
        "asset_tag",
        "name",
        "category",
        "facility",
        "department",
        "status",
        "next_service_due",
        "next_calibration_due",
    )
    list_filter = (ServiceDueFilter, "status", "category", "facility")
    search_fields = ("asset_tag", "name", "serial_number", "manufacturer")
    fieldsets = (
        (None, {"fields": ("organization", "asset_tag", "name", "category", "notes")}),
        ("Where", {"fields": ("facility", "department", "ward", "room", "location_note")}),
        ("Make", {"fields": ("manufacturer", "model_name", "serial_number")}),
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
        (
            "Dates",
            {
                "fields": (
                    "purchased_on",
                    "warranty_until",
                    "last_service_on",
                    "next_service_due",
                    "last_calibrated_on",
                    "next_calibration_due",
                )
            },
        ),
        ("Visits", {"fields": ("visits",)}),
        ("Record", {"fields": ("version", "created_at", "updated_at")}),
    )
    readonly_fields = ("status", "status_reason", "status_changed_at", "visits")

    def get_readonly_fields(self, request, obj=None):
        readonly = super().get_readonly_fields(request, obj)
        # The label's number and the owning facility are set once.
        return [*readonly, "asset_tag", "facility"] if obj else readonly

    @admin.display(description="Last visits")
    def visits(self, obj):
        """A read-only field, not an inline, so saving this page needs nothing extra."""
        records = obj.service_records.all()[:20] if obj and obj.pk else []
        if not records:
            return "No visits recorded yet."
        rows = format_html_join(
            "",
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>",
            (
                (r.performed_on, r.get_kind_display(), r.performed_by or "—", r.notes or "—")
                for r in records
            ),
        )
        return format_html(
            "<table><tr><th>Date</th><th>Kind</th><th>By</th><th>Notes</th></tr>{}</table>", rows
        )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        status = form.cleaned_data.get("new_status")
        if status:
            try:
                services.change_status(
                    actor=request.user,
                    equipment_id=obj.pk,
                    version=obj.version,
                    status=status,
                    reason=form.cleaned_data.get("new_status_reason", ""),
                    request=request,
                )
            except DomainError as exc:
                self.message_user(request, str(exc.detail), messages.ERROR)


@admin.register(EquipmentServiceRecord)
class EquipmentServiceRecordAdmin(HimsModelAdmin):
    """Add a visit through the same rules as the app. Existing visits cannot be changed: a mistake
    is corrected by adding another record."""

    list_display = ("performed_on", "equipment", "kind", "performed_by", "next_due", "recorded_by")
    list_filter = ("kind", "facility")
    search_fields = ("equipment__asset_tag", "equipment__name", "performed_by")
    date_hierarchy = "performed_on"
    fields = (
        "equipment",
        "kind",
        "performed_on",
        "performed_by",
        "notes",
        "next_due",
        "facility",
        "recorded_by",
        "recorded_at",
    )
    readonly_fields = ("facility", "recorded_by", "recorded_at")

    def has_change_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        services.record_service(actor=request.user, record=obj, request=request)
