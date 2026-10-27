from rest_framework import serializers

from apps.facilities.models import Facility

SETTING_CHOICES = [("default", "Use the default"), ("on", "On"), ("off", "Off")]


class FeatureSettingSerializer(serializers.Serializer):
    """One stored setting (hospital-wide or for a facility)."""

    setting = serializers.ChoiceField(SETTING_CHOICES)
    version = serializers.IntegerField(help_text="0 = never set; send it back when changing.")
    reason = serializers.CharField(allow_blank=True)
    updated_by_name = serializers.CharField(allow_null=True)
    updated_at = serializers.DateTimeField(allow_null=True)


class FeatureStateSerializer(serializers.Serializer):
    key = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    category = serializers.CharField()
    scope = serializers.ChoiceField(
        [("organization", "Whole hospital"), ("facility", "Per facility")]
    )
    available = serializers.BooleanField(help_text="False = not built yet (see planned_phase).")
    planned_phase = serializers.CharField(allow_blank=True)
    countries = serializers.ListField(child=serializers.CharField(), allow_null=True)
    offered_in_country = serializers.BooleanField()
    default = serializers.BooleanField(help_text="Default for this hospital's country.")
    hospital = FeatureSettingSerializer()
    facility = FeatureSettingSerializer(
        allow_null=True, help_text="Only when ?facility= is given and the feature is per facility."
    )
    enabled = serializers.BooleanField(help_text="On or off right now (for the facility if given).")


class FeatureChangeSerializer(serializers.Serializer):
    facility = serializers.PrimaryKeyRelatedField(
        queryset=Facility.objects.all(), required=False, allow_null=True
    )
    setting = serializers.ChoiceField(SETTING_CHOICES)
    reason = serializers.CharField(max_length=255)
    version = serializers.IntegerField(min_value=0)


class EffectiveFeaturesSerializer(serializers.Serializer):
    hospital = serializers.DictField(child=serializers.BooleanField())
    facilities = serializers.DictField(
        child=serializers.DictField(child=serializers.BooleanField()),
        help_text="Per-facility features, by facility id (signed-in users only).",
    )
