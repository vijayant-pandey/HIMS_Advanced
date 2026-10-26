from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=512, trim_whitespace=False, write_only=True)


class InvitationTokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512, trim_whitespace=True)


class InvitationAcceptSerializer(InvitationTokenSerializer):
    password = serializers.CharField(max_length=512, trim_whitespace=False, write_only=True)


class InvitationDetailsSerializer(serializers.Serializer):
    email = serializers.EmailField()
    display_name = serializers.CharField()
    organization_name = serializers.CharField()
    expires_at = serializers.DateTimeField()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class PasswordResetTokenSerializer(InvitationTokenSerializer):
    pass


class PasswordResetConfirmSerializer(InvitationAcceptSerializer):
    pass


class PasswordResetRequestedSerializer(serializers.Serializer):
    detail = serializers.CharField()


class PasswordResetDetailsSerializer(serializers.Serializer):
    email = serializers.EmailField()
    expires_at = serializers.DateTimeField()


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


class NoAccessReportSerializer(serializers.Serializer):
    page = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class NoAccessReferenceSerializer(serializers.Serializer):
    reference = serializers.CharField(help_text="Quote this to an administrator or support.")
