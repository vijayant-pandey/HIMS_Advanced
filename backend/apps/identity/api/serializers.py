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
    passkeys = serializers.IntegerField(help_text="Passkeys added as a second factor.")


class OrganizationSummarySerializer(serializers.Serializer):
    display_name = serializers.CharField()
    country = serializers.CharField()


class CurrentUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    display_name = serializers.CharField()
    staff_member_id = serializers.UUIDField(allow_null=True)
    grants = GrantSerializer(many=True, help_text="For navigation only; the API enforces access.")
    mfa = MfaStatusSerializer()
    organization = OrganizationSummarySerializer(
        allow_null=True, help_text="This hospital's name and country (IN/US), for display."
    )


class NoAccessReportSerializer(serializers.Serializer):
    page = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class NoAccessReferenceSerializer(serializers.Serializer):
    reference = serializers.CharField(help_text="Quote this to an administrator or support.")


class MfaChallengeSerializer(serializers.Serializer):
    mfa_required = serializers.BooleanField()
    passkey_available = serializers.BooleanField(
        help_text="The person may answer with a passkey instead of a code (HIMS-IAM-014)."
    )
    detail = serializers.CharField()


class ConfirmIdentitySerializer(serializers.Serializer):
    password = serializers.CharField(trim_whitespace=False, max_length=256)
    code = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=32,
        help_text="Authenticator or backup code, if the person uses two-factor.",
    )
    passkey = serializers.JSONField(
        required=False,
        allow_null=True,
        default=None,
        help_text="Instead of the code: the passkey's answer to "
        "/confirm-identity/passkey-options/.",
    )


class ConfirmIdentityStatusSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(help_text="Off if the hospital turned the feature off.")
    confirmed = serializers.BooleanField(help_text="Sensitive actions will not ask right now.")
    confirmed_until = serializers.DateTimeField(allow_null=True)
    window_minutes = serializers.IntegerField()
    needs_code = serializers.BooleanField()
    passkey_available = serializers.BooleanField()


class MfaCodeSerializer(serializers.Serializer):
    code = serializers.CharField(
        max_length=32, help_text="6-digit authenticator code, or a recovery code where allowed."
    )


class MfaSetupSerializer(serializers.Serializer):
    secret = serializers.CharField(help_text="Shown once, for typing into the app by hand.")
    otpauth_uri = serializers.CharField(help_text="Encode as a QR code for the authenticator app.")


class MfaRecoveryCodesSerializer(serializers.Serializer):
    recovery_codes = serializers.ListField(child=serializers.CharField())


class MySessionSerializer(serializers.Serializer):
    """One of the person's own sign-ins (HIMS-IAM-016). The session key is never sent."""

    id = serializers.UUIDField()
    device = serializers.CharField(help_text='Readable device, e.g. "Chrome on Windows".')
    ip_address = serializers.IPAddressField(allow_null=True)
    signed_in_at = serializers.DateTimeField(source="created_at")
    is_current = serializers.BooleanField(help_text="The device making this request.")


class SessionsEndedSerializer(serializers.Serializer):
    sessions_ended = serializers.IntegerField()


class PasskeySerializer(serializers.Serializer):
    """One of the person's passkeys (HIMS-IAM-014). The key itself is never sent."""

    id = serializers.UUIDField()
    name = serializers.CharField()
    backed_up = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    last_used_at = serializers.DateTimeField(allow_null=True)


class PasskeyOptionsSerializer(serializers.Serializer):
    public_key = serializers.JSONField(
        help_text="WebAuthn options for navigator.credentials (binary values as base64url)."
    )


class PasskeyCredentialSerializer(serializers.Serializer):
    credential = serializers.JSONField(
        help_text="The browser's answer, binary values as base64url."
    )


class PasskeyAddSerializer(PasskeyCredentialSerializer):
    name = serializers.CharField(max_length=60, help_text='e.g. "Work laptop".')
