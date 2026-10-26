from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.access_control.selectors import list_grants
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction, record_audit_event
from apps.organizations.models import Organization
from common.exceptions import DomainError

from .. import invitations
from .serializers import (
    CurrentUserSerializer,
    InvitationAcceptSerializer,
    InvitationDetailsSerializer,
    InvitationTokenSerializer,
    LoginSerializer,
)


class InvalidCredentials(DomainError):
    status_code = 401
    code = "INVALID_CREDENTIALS"
    title = "Sign-in failed"


def _current_user_payload(user) -> dict:
    staff_member = getattr(user, "staff_member", None)
    return {
        "id": user.pk,
        "email": user.email,
        "display_name": user.display_name,
        "staff_member_id": staff_member.pk if staff_member else None,
        "grants": list_grants(user),
    }


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
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(request=LoginSerializer, responses={200: CurrentUserSerializer})
    def post(self, request):
        SessionAuthentication().enforce_csrf(request)  # login CSRF protection
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        user = authenticate(
            request._request, email=email, password=serializer.validated_data["password"]
        )
        if user is None:
            # Same response for unknown, inactive and wrong-password accounts (spec 13.1).
            record_audit_event(
                action=AuditAction.AUTH_LOGIN_FAILED,
                resource_type="session",
                request=request,
                outcome=AuditEvent.Outcome.FAILURE,
            )
            raise InvalidCredentials("Email or password is incorrect.")
        login(request._request, user)  # rotates the session key (prevents fixation)
        record_audit_event(
            action=AuditAction.AUTH_LOGIN, resource_type="session", actor=user, request=request
        )
        return Response(CurrentUserSerializer(_current_user_payload(user)).data)


class _PublicInvitationView(APIView):
    """Invitation endpoints are used before the person has a password, so they are public,
    CSRF-protected and rate limited. The token comes in the body, never in the URL."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
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
        login(request._request, user, backend="django.contrib.auth.backends.ModelBackend")
        record_audit_event(
            action=AuditAction.AUTH_LOGIN,
            resource_type="session",
            actor=user,
            request=request,
            metadata={"via": "invitation"},
        )
        return Response(CurrentUserSerializer(_current_user_payload(user)).data)


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
        return Response(CurrentUserSerializer(_current_user_payload(request.user)).data)
