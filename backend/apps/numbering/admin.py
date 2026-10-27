from django import forms
from django.contrib import admin, messages

from common.admin.options import HimsModelAdmin, ReadOnlyModelAdmin
from common.exceptions import DomainError

from .models import IssuedNumber, NumberCounter, NumberingScheme
from .services import example_number, next_number_preview, set_next_number


class NumberingSchemeForm(forms.ModelForm):
    continue_from = forms.IntegerField(
        required=False,
        min_value=1,
        label="Set next running number",
        help_text="Only when moving from another system, e.g. its last MRN was 54321 → enter "
        "54322. It can only move forward.",
    )

    class Meta:
        model = NumberingScheme
        fields = (  # organization is always this deployment's hospital
            "document_type",
            "facility",
            "is_active",
            "prefix",
            "separator",
            "include_facility_code",
            "period",
            "year_format",
            "financial_year_start_month",
            "padding",
            "start_at",
        )


@admin.register(NumberingScheme)
class NumberingSchemeAdmin(HimsModelAdmin):
    form = NumberingSchemeForm
    list_display = ("document_type", "scope", "next_number", "period", "is_active")
    list_filter = ("document_type", "is_active", "period")
    fieldsets = (
        (None, {"fields": ("document_type", "facility", "is_active")}),
        (
            "Format",
            {
                "fields": (
                    "prefix",
                    "separator",
                    "include_facility_code",
                    "period",
                    "year_format",
                    "financial_year_start_month",
                    "padding",
                    "start_at",
                    "example",
                )
            },
        ),
        ("Continue numbering", {"fields": ("next_number", "continue_from")}),
        ("Record", {"fields": ("version", "created_at", "updated_at")}),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = [*super().get_readonly_fields(request, obj), "example", "next_number"]
        if obj is not None:
            readonly += ["document_type", "facility"]  # create a new scheme instead
        return readonly

    @admin.display(description="Applies to")
    def scope(self, obj):
        return obj.facility.name if obj.facility_id else "Whole hospital"

    @admin.display(description="Example")
    def example(self, obj):
        return example_number(obj) if obj and obj.pk else "Shown after saving"

    @admin.display(description="Next number")
    def next_number(self, obj):
        return next_number_preview(obj) if obj and obj.pk else "—"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        next_value = form.cleaned_data.get("continue_from")
        if next_value:
            try:
                set_next_number(
                    actor=request.user,
                    scheme_id=obj.pk,
                    version=obj.version,
                    next_value=next_value,
                    request=request,
                )
            except DomainError as exc:
                self.message_user(request, f"Next number not changed: {exc}", messages.WARNING)


@admin.register(NumberCounter)
class NumberCounterAdmin(ReadOnlyModelAdmin):
    list_display = ("scheme", "period_key", "last_value", "updated_at")
    list_filter = ("scheme__document_type",)


@admin.register(IssuedNumber)
class IssuedNumberAdmin(ReadOnlyModelAdmin):
    list_display = ("value", "document_type", "facility", "issued_by", "reference", "created_at")
    list_filter = ("document_type", "facility")
    search_fields = ("value", "reference")
    date_hierarchy = "created_at"
