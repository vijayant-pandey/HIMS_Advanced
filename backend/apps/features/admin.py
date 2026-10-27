from django import forms
from django.contrib import admin

from common.admin.options import HimsModelAdmin

from . import catalog
from .models import FeatureFlag
from .services import current_settings

SETTING_CHOICES = [("", "Use the default"), ("true", "On"), ("false", "Off")]


class FeatureFlagForm(forms.ModelForm):
    key = forms.ChoiceField(
        choices=[(f.key, f"{f.name} ({f.key})") for f in catalog.FEATURES], label="Feature"
    )
    enabled = forms.TypedChoiceField(
        choices=SETTING_CHOICES,
        coerce=lambda value: value == "true",
        empty_value=None,
        required=False,
        label="Setting",
    )

    class Meta:
        model = FeatureFlag
        fields = ("key", "facility", "enabled", "reason")  # organization: this hospital


@admin.register(FeatureFlag)
class FeatureFlagAdmin(HimsModelAdmin):
    """Every feature appears here: hospital-wide rows are created automatically ("use the
    default"); add a row with a facility to set a per-facility feature for one facility."""

    form = FeatureFlagForm
    list_display = (
        "name",
        "key",
        "applies_to",
        "setting",
        "default_value",
        "now",
        "availability",
        "reason",
        "updated_by",
    )
    list_filter = ("enabled", "facility")
    search_fields = ("key", "reason")
    readonly_fields = ("description", "availability", "default_value", "now", "updated_by")
    fieldsets = (
        (None, {"fields": ("key", "description", "availability", "facility")}),
        ("Setting", {"fields": ("enabled", "reason", "default_value", "now")}),
        ("Record", {"fields": ("updated_by", "version", "created_at", "updated_at")}),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            readonly += ["key", "facility"]
        return readonly

    @admin.display(description="Feature")
    def name(self, obj):
        return obj.feature.name if obj.feature else f"{obj.key} (retired)"

    @admin.display(description="What it does")
    def description(self, obj):
        return obj.feature.description if obj and obj.feature else "—"

    @admin.display(description="Applies to")
    def applies_to(self, obj):
        return obj.facility.name if obj.facility_id else "Whole hospital"

    @admin.display(description="Setting")
    def setting(self, obj):
        return {None: "Default", True: "On", False: "Off"}[obj.enabled]

    @admin.display(description="Default")
    def default_value(self, obj):
        if not obj or not obj.feature:
            return "—"
        return "On" if current_settings().default(obj.feature) else "Off"

    @admin.display(description="On right now")
    def now(self, obj):
        if not obj or not obj.feature:
            return "—"
        return "On" if current_settings().at(obj.feature, obj.facility_id) else "Off"

    @admin.display(description="Available")
    def availability(self, obj):
        feature = obj.feature if obj else None
        if feature is None:
            return "—"
        if not feature.available:
            return f"Coming in {feature.planned_phase}"
        if feature.countries:
            return "Yes, in " + ", ".join(sorted(feature.countries))
        return "Yes"

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
