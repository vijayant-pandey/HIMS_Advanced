from rest_framework import serializers

from common.validators import validate_timezone

from ..models import Organization


class OrganizationSerializer(serializers.ModelSerializer):
    has_logo = serializers.SerializerMethodField()

    def get_has_logo(self, organization) -> bool:
        return bool(organization.logo)

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
            "has_logo",
            "letterhead_address",
            "letterhead_phone",
            "letterhead_email",
            "letterhead_website",
            "letterhead_registration",
            "letterhead_footer",
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
    letterhead_address = serializers.CharField(max_length=500, required=False, allow_blank=True)
    letterhead_phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    letterhead_email = serializers.EmailField(required=False, allow_blank=True)
    letterhead_website = serializers.CharField(max_length=200, required=False, allow_blank=True)
    letterhead_registration = serializers.CharField(
        max_length=120, required=False, allow_blank=True
    )
    letterhead_footer = serializers.CharField(max_length=255, required=False, allow_blank=True)


class LetterheadSerializer(serializers.Serializer):
    """What goes at the top and bottom of a printout. Any signed-in person may read it: they
    may need to print, and it is what the hospital prints for everyone."""

    display_name = serializers.CharField()
    legal_name = serializers.CharField()
    lines = serializers.ListField(child=serializers.CharField())
    has_logo = serializers.BooleanField()
    version = serializers.IntegerField(help_text="Changes when the logo or details change")


class LogoUploadSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="PNG or JPG, up to 2 MB")
