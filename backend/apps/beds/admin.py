from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html, format_html_join

from apps.facilities.admin import RoomAdmin, _LocationAdmin
from common.admin.options import HimsInline, ReadOnlyModelAdmin
from common.exceptions import DomainError

from . import board
from .models import Bed, BedStatusChange
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
    change_list_template = "admin/beds/bed/change_list.html"
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
        ("Status history", {"fields": ("status_history",)}),
        ("Record", {"fields": ("version", "created_at", "updated_at")}),
    )
    readonly_fields = ("status", "status_reason", "status_changed_at", "status_history")

    @admin.display(description="Last changes")
    def status_history(self, obj):
        """The bed's last status changes (HIMS-FAC-008). A read-only field, not an inline, so
        saving the bed page needs nothing extra; the database refuses edits anyway."""
        changes = board.bed_history(obj) if obj and obj.pk else []
        if not changes:
            return "No status changes yet."
        rows = format_html_join(
            "",
            "<tr><td>{}</td><td>{} → {}</td><td>{}</td><td>{}</td></tr>",
            (
                (
                    c.changed_at.strftime("%Y-%m-%d %H:%M"),
                    c.get_from_status_display(),
                    c.get_to_status_display(),
                    c.reason or "—",
                    c.changed_by.display_name if c.changed_by else "—",
                )
                for c in changes
            ),
        )
        return format_html(
            "<table><thead><tr><th>When (UTC)</th><th>Change</th><th>Why</th><th>Who</th></tr>"
            "</thead><tbody>{}</tbody></table>",
            rows,
        )

    actions = ["mark_available", "mark_out_of_service"]

    def get_urls(self):
        return [
            path(
                "board/",
                self.admin_site.admin_view(self.board_view),
                name="beds_bed_board",
            ),
            *super().get_urls(),
        ]

    def board_view(self, request):
        """The bed board in the console: each ward's beds by status, for one facility, with the
        same visibility rules as the app's Bed board page (HIMS-FAC-008)."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        data = board.build_board(
            request.user, facility_id=request.GET.get("facility") or None, request=request
        )
        statuses = list(Bed.Status)
        wards = [
            {
                **ward,
                "counts": [ward["bed_counts"].get(status.value, 0) for status in statuses],
                "unavailable": [b for b in ward["beds"] if b["status"] != Bed.Status.AVAILABLE],
            }
            for ward in data["wards"]
        ]
        context = {
            **self.admin_site.each_context(request),
            "title": "Bed board",
            "opts": self.model._meta,
            "board": data,
            "statuses": statuses,
            "totals": [data["bed_counts"].get(status.value, 0) for status in statuses],
            "wards": wards,
            "type_labels": dict(Bed.BedType.choices),
        }
        return TemplateResponse(request, "admin/beds/bed/board.html", context)

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


@admin.register(BedStatusChange)
class BedStatusChangeAdmin(ReadOnlyModelAdmin):
    """Every bed status change (HIMS-FAC-008). Append-only: the database refuses changes."""

    list_display = ("changed_at", "bed", "ward", "from_status", "to_status", "reason", "changed_by")
    list_filter = ("to_status", "facility")
    search_fields = ("bed__code", "ward__code", "reason")
    date_hierarchy = "changed_at"
    list_select_related = ("bed__ward", "ward", "changed_by")
