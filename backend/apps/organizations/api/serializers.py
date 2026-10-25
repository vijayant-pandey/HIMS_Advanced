from rest_framework import serializers

from common.validators import validate_timezone

from ..models import Organization


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = [
            "id",
            "legal_name",
            "display_name",
            "country",
            "default_timezone",
            "default_currency",
            "status",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class OrganizationUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    legal_name = serializers.CharField(max_length=255, required=False)
    display_name = serializers.CharField(max_length=255, required=False)
    default_timezone = serializers.CharField(
        max_length=64, required=False, validators=[validate_timezone]
    )
