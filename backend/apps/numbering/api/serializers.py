from rest_framework import serializers

from apps.facilities.models import Facility

from ..models import IssuedNumber, NumberingScheme

SETTINGS_FIELDS = [
    "prefix",
    "separator",
    "include_facility_code",
    "period",
    "year_format",
    "financial_year_start_month",
    "padding",
    "start_at",
]

SETTINGS_LIMITS = {
    "padding": {"min_value": 3, "max_value": 12},
    "financial_year_start_month": {"min_value": 1, "max_value": 12},
}


class NumberingSchemeSerializer(serializers.ModelSerializer):
    document_type_label = serializers.CharField(source="get_document_type_display", read_only=True)
    facility_name = serializers.CharField(
        source="facility.name", default=None, allow_null=True, read_only=True
    )
    next_number = serializers.SerializerMethodField(
        help_text="The number the next record will get (not used up by viewing it)."
    )

    class Meta:
        model = NumberingScheme
        fields = [
            "id",
            "document_type",
            "document_type_label",
            "facility",
            "facility_name",
            *SETTINGS_FIELDS,
            "is_active",
            "next_number",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_next_number(self, scheme) -> str:
        from ..services import next_number_preview

        return next_number_preview(scheme)


class NumberingSchemeCreateSerializer(serializers.ModelSerializer):
    facility = serializers.PrimaryKeyRelatedField(
        queryset=Facility.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = NumberingScheme
        fields = ["document_type", "facility", *SETTINGS_FIELDS]
        extra_kwargs = SETTINGS_LIMITS
        validators = []  # the model explains duplicates in plain words (400)


class NumberingSchemeUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    prefix = serializers.CharField(max_length=10, allow_blank=True, required=False)
    separator = serializers.ChoiceField(NumberingScheme.Separator.choices, required=False)
    include_facility_code = serializers.BooleanField(required=False)
    period = serializers.ChoiceField(NumberingScheme.Period.choices, required=False)
    year_format = serializers.ChoiceField(NumberingScheme.YearFormat.choices, required=False)
    financial_year_start_month = serializers.IntegerField(min_value=1, max_value=12, required=False)
    padding = serializers.IntegerField(min_value=3, max_value=12, required=False)
    start_at = serializers.IntegerField(min_value=0, required=False)
    is_active = serializers.BooleanField(required=False)


class NumberingPreviewRequestSerializer(serializers.ModelSerializer):
    """Settings to try out before saving; nothing is stored."""

    facility = serializers.PrimaryKeyRelatedField(
        queryset=Facility.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = NumberingScheme
        fields = ["document_type", "facility", *SETTINGS_FIELDS]
        extra_kwargs = SETTINGS_LIMITS
        validators = []


class NumberingPreviewSerializer(serializers.Serializer):
    example = serializers.CharField(help_text="What the first number would look like today.")
    longest = serializers.CharField(help_text="The longest number this format can produce.")
    errors = serializers.DictField(
        child=serializers.ListField(child=serializers.CharField()),
        help_text="Problems with these settings (empty when they can be saved).",
    )


class SetNextNumberSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    next_value = serializers.IntegerField(
        min_value=1, help_text="Running number the next record should get, e.g. 54322."
    )


class IssuedNumberSerializer(serializers.ModelSerializer):
    issued_by_name = serializers.CharField(
        source="issued_by.display_name", default=None, allow_null=True, read_only=True
    )

    class Meta:
        model = IssuedNumber
        fields = [
            "id",
            "document_type",
            "value",
            "facility",
            "period_key",
            "sequence",
            "issued_by",
            "issued_by_name",
            "reference",
            "created_at",
        ]
        read_only_fields = fields
