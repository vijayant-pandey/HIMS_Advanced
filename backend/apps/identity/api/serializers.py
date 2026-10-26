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


class MfaStatusSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(help_text="Two-factor sign-in is on for this account.")
    required = serializers.BooleanField(help_text="The person's role requires two-factor.")
    verified = serializers.BooleanField(help_text="This session passed two-factor.")
    recovery_codes_remaining = serializers.IntegerField()


class CurrentUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    display_name = serializers.CharField()
    staff_member_id = serializers.UUIDField(allow_null=True)
    grants = GrantSerializer(many=True, help_text="For navigation only; the API enforces access.")
    mfa = MfaStatusSerializer()


class NoAccessReportSerializer(serializers.Serializer):
    page = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class NoAccessReferenceSerializer(serializers.Serializer):
    reference = serializers.CharField(help_text="Quote this to an administrator or support.")


class MfaChallengeSerializer(serializers.Serializer):
    mfa_required = serializers.BooleanField()
    detail = serializers.CharField()


class MfaCodeSerializer(serializers.Serializer):
    code = serializers.CharField(
        max_length=32, help_text="6-digit authenticator code, or a recovery code where allowed."
    )


class MfaSetupSerializer(serializers.Serializer):
    secret = serializers.CharField(help_text="Shown once, for typing into the app by hand.")
    otpauth_uri = serializers.CharField(help_text="Encode as a QR code for the authenticator app.")


class MfaRecoveryCodesSerializer(serializers.Serializer):
    recovery_codes = serializers.ListField(child=serializers.CharField())
