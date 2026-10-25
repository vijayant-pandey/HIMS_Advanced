from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=512, trim_whitespace=False, write_only=True)


class GrantSerializer(serializers.Serializer):
    permission = serializers.CharField()
    facility_id = serializers.UUIDField(allow_null=True)
    department_id = serializers.UUIDField(allow_null=True)


class CurrentUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    display_name = serializers.CharField()
    staff_member_id = serializers.UUIDField(allow_null=True)
    grants = GrantSerializer(many=True, help_text="For navigation only; the API enforces access.")
