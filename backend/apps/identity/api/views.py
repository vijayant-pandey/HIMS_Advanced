from datetime import timedelta

from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.selectors import list_grants
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction, record_audit_event
from apps.features.catalog import F
from apps.features.services import require_enabled
from apps.organizations.models import Organization
from common.exceptions import ConflictError, DomainError
from common.throttling import ScopedThrottle

from .. import (
    confirmation,
    invitations,
    mfa,
    passkeys,
    password_reset,
    sessions,
    sign_in_limits,
)
from ..models import Passkey, UserSession
from .serializers import (
    ConfirmIdentitySerializer,
    ConfirmIdentityStatusSerializer,
    CurrentUserSerializer,
    InvitationAcceptSerializer,
    InvitationDetailsSerializer,
    InvitationTokenSerializer,
    LoginSerializer,
    MfaChallengeSerializer,
    MfaCodeSerializer,
    MfaRecoveryCodesSerializer,
    MfaSetupSerializer,
    MfaStatusSerializer,
    MySessionSerializer,
    NoAccessReferenceSerializer,
    NoAccessReportSerializer,
    PasskeyAddSerializer,
    PasskeyCredentialSerializer,
    PasskeyOptionsSerializer,
    PasskeySerializer,
    PasswordResetConfirmSerializer,
    PasswordResetDetailsSerializer,
    PasswordResetRequestedSerializer,
    PasswordResetRequestSerializer,
    PasswordResetTokenSerializer,
    SessionsEndedSerializer,
)


class InvalidCredentials(DomainError):
    status_code = 401
    code = "INVALID_CREDENTIALS"
    title = "Sign-in failed"


def _current_user_payload(user, request=None) -> dict:
    staff_member = getattr(user, "staff_member", None)
    return {
        "id": user.pk,
        "email": user.email,
        "display_name": user.display_name,
        "staff_member_id": staff_member.pk if staff_member else None,
        "grants": list_grants(user),
        "mfa": mfa.status(user, request),
        "organization": _organization_summary(),
    }


def _organization_summary() -> dict | None:
    from apps.organizations.models import Organization

    organization = Organization.objects.values("display_name", "country").first()
    return organization  # None only before provisioning


def _complete_login(request, user, *, via: str, mfa_verified: bool) -> Response:
    """Create the session (rotating its key against fixation), record it and answer with the
    current-user payload."""
    login(request._request, user, backend="django.contrib.auth.backends.ModelBackend")
    mfa.mark_session_verified(request, mfa_verified)
    record_audit_event(
        action=AuditAction.AUTH_LOGIN,
        resource_type="session",
        actor=user,
        request=request,
        metadata={"via": via, "mfa": mfa_verified},
    )
    return Response(CurrentUserSerializer(_current_user_payload(user, request)).data)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfTokenView(APIView):
    """Sets the CSRF cookie the SPA must echo in X-CSRFToken on unsafe requests."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses={204: None})
    def get(self, request):
        return Response(status=status.HTTP_204_NO_CONTENT)


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedThrottle]
    throttle_scope = "login"

    @extend_schema(
        request=LoginSerializer,
        responses={200: CurrentUserSerializer, 202: MfaChallengeSerializer},
        description="200 = signed in. 202 = password accepted; send the authenticator code to "
        "/auth/login/verify/ to finish signing in.",
    )
    def post(self, request):
        SessionAuthentication().enforce_csrf(request)  # login CSRF protection
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        try:
            sign_in_limits.check(email)  # per account, on top of the per-address rate limit
        except sign_in_limits.SignInPaused:
            record_audit_event(
                action=AuditAction.AUTH_LOGIN_FAILED,
                resource_type="session",
                request=request,
                outcome=AuditEvent.Outcome.FAILURE,
                metadata={"reason": "paused"},
            )
            raise
        user = authenticate(
            request._request, email=email, password=serializer.validated_data["password"]
        )
        if user is None:
            sign_in_limits.record_failure(email)
            # Same response for unknown, inactive and wrong-password accounts (spec 13.1).
            record_audit_event(
                action=AuditAction.AUTH_LOGIN_FAILED,
                resource_type="session",
                request=request,
                outcome=AuditEvent.Outcome.FAILURE,
            )
            raise InvalidCredentials("Email or password is incorrect.")
        sign_in_limits.clear(email)
        if mfa.confirmed_device(user) is not None:
            mfa.begin_challenge(request, user)
            return Response(
                {
                    "mfa_required": True,
                    "passkey_available": passkeys.available(user),
                    "detail": "Enter the 6-digit code from your authenticator app.",
                },
                status=status.HTTP_202_ACCEPTED,
            )
        return _complete_login(request, user, via="password", mfa_verified=False)


class LoginVerifyView(APIView):
    """Second sign-in step for accounts with two-factor on (HIMS-IAM-005)."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedThrottle]
    throttle_scope = "login"

    @extend_schema(request=MfaCodeSerializer, responses={200: CurrentUserSerializer})
    def post(self, request):
        SessionAuthentication().enforce_csrf(request)
        serializer = MfaCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = mfa.verify_challenge(request, serializer.validated_data["code"])
        return _complete_login(request, user, via="password+mfa", mfa_verified=True)


class LoginPasskeyOptionsView(APIView):
    """Second sign-in step with a passkey (HIMS-IAM-014): the challenge for the device to sign."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedThrottle]
    throttle_scope = "login"

    @extend_schema(request=None, responses={200: PasskeyOptionsSerializer})
    def post(self, request):
        SessionAuthentication().enforce_csrf(request)
        user, _pending = mfa.pending_challenge(request)
        return Response({"public_key": passkeys.begin_assertion(request, user, passkeys.LOGIN)})


class LoginPasskeyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedThrottle]
    throttle_scope = "login"

    @extend_schema(request=PasskeyCredentialSerializer, responses={200: CurrentUserSerializer})
    def post(self, request):
        SessionAuthentication().enforce_csrf(request)
        serializer = PasskeyCredentialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = passkeys.verify_login(request, serializer.validated_data["credential"])
        return _complete_login(request, user, via="password+passkey", mfa_verified=True)


class _PublicInvitationView(APIView):
    """Invitation endpoints are used before the person has a password, so they are public,
    CSRF-protected and rate limited. The token comes in the body, never in the URL."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedThrottle]
    throttle_scope = "invitation"


class InvitationInspectView(_PublicInvitationView):
    @extend_schema(request=InvitationTokenSerializer, responses={200: InvitationDetailsSerializer})
    def post(self, request):
        SessionAuthentication().enforce_csrf(request)
        serializer = InvitationTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = invitations.inspect_invitation(serializer.validated_data["token"])
        organization = Organization.objects.only("display_name").first()
        return Response(
            InvitationDetailsSerializer(
                {
                    "email": invitation.user.email,
                    "display_name": invitation.user.display_name,
                    "organization_name": organization.display_name if organization else "HIMS",
                    "expires_at": invitation.expires_at,
                }
            ).data
        )


class InvitationAcceptView(_PublicInvitationView):
    @extend_schema(request=InvitationAcceptSerializer, responses={200: CurrentUserSerializer})
    def post(self, request):
        SessionAuthentication().enforce_csrf(request)
        serializer = InvitationAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = invitations.accept_invitation(
            token=serializer.validated_data["token"],
            password=serializer.validated_data["password"],
            request=request,
        )
        # Activation signs the person in, like a normal login (session key rotated).
        return _complete_login(request, user, via="invitation", mfa_verified=False)


class _PublicPasswordResetView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedThrottle]
    throttle_scope = "password_reset"


RESET_REQUESTED_MESSAGE = (
    "If an active account uses this email, we have sent a link to reset the password. "
    "Check your inbox."
)


class PasswordResetRequestView(_PublicPasswordResetView):
    """Always answers 202 with the same message, whether or not the account exists."""

    @extend_schema(
        request=PasswordResetRequestSerializer, responses={202: PasswordResetRequestedSerializer}
    )
    def post(self, request):
        SessionAuthentication().enforce_csrf(request)
        # The hospital may turn self-service resets off (HIMS-ORG-004); the answer is the same for
        # every email address, so it still reveals nothing about accounts.
        require_enabled(F.SELF_SERVICE_PASSWORD_RESET, request=request)
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        password_reset.request_password_reset(
            email=serializer.validated_data["email"], request=request
        )
        return Response({"detail": RESET_REQUESTED_MESSAGE}, status=status.HTTP_202_ACCEPTED)


class PasswordResetInspectView(_PublicPasswordResetView):
    @extend_schema(
        request=PasswordResetTokenSerializer, responses={200: PasswordResetDetailsSerializer}
    )
    def post(self, request):
        SessionAuthentication().enforce_csrf(request)
        serializer = PasswordResetTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reset = password_reset.inspect_reset(serializer.validated_data["token"])
        return Response(
            PasswordResetDetailsSerializer(
                {"email": reset.user.email, "expires_at": reset.expires_at}
            ).data
        )


class PasswordResetConfirmView(_PublicPasswordResetView):
    """Sets the new password. The person then signs in again; all old sessions have ended."""

    @extend_schema(request=PasswordResetConfirmSerializer, responses={204: None})
    def post(self, request):
        SessionAuthentication().enforce_csrf(request)
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        password_reset.complete_password_reset(
            token=serializer.validated_data["token"],
            password=serializer.validated_data["password"],
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        record_audit_event(action=AuditAction.AUTH_LOGOUT, resource_type="session", request=request)
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: CurrentUserSerializer})
    def get(self, request):
        return Response(CurrentUserSerializer(_current_user_payload(request.user, request)).data)


class NoAccessReportView(APIView):
    """Called by the app when a signed-in user has no role yet (HIMS-UI-002).

    Records an ``access.none_assigned`` audit event and returns its reference number (the
    request ID), which the "no access yet" page shows so an administrator can find the event.
    The audit log cannot be cleaned up, so one event per person per 10 minutes is enough, and
    someone who already has access records nothing (HIMS-SEC-011 finding F-04).
    """

    permission_classes = [IsAuthenticated]
    REPEAT_MINUTES = 10

    @extend_schema(
        request=NoAccessReportSerializer,
        responses={200: NoAccessReferenceSerializer, 201: NoAccessReferenceSerializer},
    )
    def post(self, request):
        serializer = NoAccessReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if list_grants(request.user):
            raise ConflictError("You already have access.", code="HAS_ACCESS")
        recent = (
            AuditEvent.objects.filter(
                action=AuditAction.ACCESS_NONE_ASSIGNED,
                resource_id=str(request.user.pk),
                occurred_at__gte=timezone.now() - timedelta(minutes=self.REPEAT_MINUTES),
            )
            .order_by("-occurred_at")
            .values_list("request_id", flat=True)
            .first()
        )
        if recent:
            return Response({"reference": recent})
        event = record_audit_event(
            action=AuditAction.ACCESS_NONE_ASSIGNED,
            resource_type="user",
            resource_id=request.user.pk,
            request=request,
            outcome=AuditEvent.Outcome.DENIED,
            metadata={
                "page": serializer.validated_data["page"],
                "grant_count": 0,
            },
        )
        return Response({"reference": event.request_id}, status=status.HTTP_201_CREATED)


class ConfirmIdentityView(APIView):
    """ "Confirm it's you" before a sensitive action (HIMS-IAM-007). Only tries are rate limited."""

    permission_classes = [IsAuthenticated]
    throttle_scope = "confirm_identity"

    def get_throttles(self):
        return [ScopedThrottle()] if self.request.method == "POST" else super().get_throttles()

    @extend_schema(responses={200: ConfirmIdentityStatusSerializer})
    def get(self, request):
        return Response(ConfirmIdentityStatusSerializer(confirmation.status(request)).data)

    @extend_schema(
        request=ConfirmIdentitySerializer, responses={200: ConfirmIdentityStatusSerializer}
    )
    def post(self, request):
        serializer = ConfirmIdentitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        confirmation.confirm(request, **serializer.validated_data)
        return Response(ConfirmIdentityStatusSerializer(confirmation.status(request)).data)


class ConfirmIdentityPasskeyOptionsView(APIView):
    """The challenge for answering "confirm it's you" with a passkey (HIMS-IAM-014)."""

    permission_classes = [IsAuthenticated]
    throttle_scope = "confirm_identity"
    throttle_classes = [ScopedThrottle]

    @extend_schema(request=None, responses={200: PasskeyOptionsSerializer})
    def post(self, request):
        return Response(
            {"public_key": passkeys.begin_assertion(request, request.user, passkeys.CONFIRM)}
        )


class EndIdentityConfirmationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: ConfirmIdentityStatusSerializer})
    def post(self, request):
        confirmation.end(request)
        return Response(ConfirmIdentityStatusSerializer(confirmation.status(request)).data)


class MfaStatusView(APIView):
    """Two-factor status for the signed-in user. Always reachable, so people can set it up."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: MfaStatusSerializer})
    def get(self, request):
        return Response(MfaStatusSerializer(mfa.status(request.user, request)).data)


class MfaSetupView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={201: MfaSetupSerializer})
    def post(self, request):
        return Response(
            MfaSetupSerializer(mfa.begin_setup(request.user)).data, status=status.HTTP_201_CREATED
        )


class MfaConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=MfaCodeSerializer, responses={200: MfaRecoveryCodesSerializer})
    def post(self, request):
        serializer = MfaCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        codes = mfa.confirm_setup(
            user=request.user, code=serializer.validated_data["code"], request=request
        )
        return Response({"recovery_codes": codes})


class MfaRecoveryCodesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=MfaCodeSerializer, responses={200: MfaRecoveryCodesSerializer})
    def post(self, request):
        serializer = MfaCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        codes = mfa.regenerate_recovery_codes(
            user=request.user, code=serializer.validated_data["code"], request=request
        )
        return Response({"recovery_codes": codes})


class MfaDisableView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=MfaCodeSerializer, responses={204: None})
    def post(self, request):
        serializer = MfaCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mfa.disable(user=request.user, code=serializer.validated_data["code"], request=request)
        mfa.mark_session_verified(request, False)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MySessionsView(APIView):
    """ "My sign-ins" (HIMS-IAM-016): the person's own open sessions, newest first."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: MySessionSerializer(many=True)})
    def get(self, request):
        current = request.session.session_key
        rows = [
            {
                "id": entry.pk,
                "device": sessions.describe_device(entry.user_agent),
                "ip_address": entry.ip_address,
                "created_at": entry.created_at,
                "is_current": entry.session_key == current,
            }
            for entry in sessions.open_sessions_for(request.user)
        ]
        return Response(MySessionSerializer(rows, many=True).data)


class MySessionEndView(APIView):
    """Sign out one of the person's other devices."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def post(self, request, session_id):
        sessions.end_own_session(user=request.user, session_id=session_id, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MySessionsEndOthersView(APIView):
    """Sign out every device except this one (e.g. after a lost phone)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: SessionsEndedSerializer})
    def post(self, request):
        ended = sessions.end_user_sessions(
            request.user,
            reason=UserSession.EndReason.SIGNED_OUT_BY_USER,
            actor=request.user,
            request=request,
            keep_session_key=request.session.session_key,
        )
        return Response({"sessions_ended": ended})


class PasskeysView(APIView):
    """Your passkeys (HIMS-IAM-014)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: PasskeySerializer(many=True)})
    def get(self, request):
        rows = Passkey.objects.filter(user=request.user)
        return Response(PasskeySerializer(rows, many=True).data)


class PasskeyAddOptionsView(APIView):
    """Start adding a passkey. Sensitive: needs a recent "confirm it's you"."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: PasskeyOptionsSerializer})
    def post(self, request):
        confirmation.require(request)
        return Response({"public_key": passkeys.begin_registration(request, request.user)})


class PasskeyAddView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=PasskeyAddSerializer, responses={201: PasskeySerializer})
    def post(self, request):
        confirmation.require(request)
        serializer = PasskeyAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        passkey = passkeys.finish_registration(
            request,
            request.user,
            name=serializer.validated_data["name"],
            credential=serializer.validated_data["credential"],
        )
        return Response(PasskeySerializer(passkey).data, status=status.HTTP_201_CREATED)


class PasskeyRemoveView(APIView):
    """Remove one of your passkeys. Sensitive: needs a recent "confirm it's you"."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def post(self, request, passkey_id):
        confirmation.require(request)
        passkeys.remove(
            actor=request.user, passkey_id=passkey_id, owner=request.user, request=request
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
