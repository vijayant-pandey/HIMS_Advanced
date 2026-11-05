"""Confirm it's you before a sensitive action (HIMS-IAM-007; spec 13.1).

A stolen or unattended session should not be enough to change who can do what. Sensitive actions
need the person's password, and their authenticator code if they use one, within the last
HIMS_CONFIRM_IDENTITY_MINUTES. Signing in counts. The time is kept in the session, so it ends with
the session and never carries over to another device.

API views list their sensitive actions in ``sensitive_actions`` (common.permissions enforces it)
and the admin console uses ConfirmIdentityAdminMixin. See docs/workflows/sensitive-actions.md.
"""

from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.contrib.auth import logout
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction, record_audit_event
from apps.features.catalog import F
from apps.features.services import is_enabled
from common.exceptions import DomainError

from . import mfa

SESSION_CONFIRMED_KEY = "hims_identity_confirmed_at"
SESSION_FAILURES_KEY = "hims_identity_confirm_failures"
MAX_FAILURES = 5


class IdentityConfirmationRequired(DomainError):
    status_code = 403
    code = "REAUTH_REQUIRED"
    title = "Please confirm it's you"


class IdentityNotConfirmed(DomainError):
    status_code = 400
    code = "REAUTH_FAILED"
    title = "Not confirmed"


class IdentityConfirmationLocked(DomainError):
    status_code = 401
    code = "REAUTH_LOCKED"
    title = "Signed out"


def _window() -> timedelta:
    return timedelta(minutes=settings.HIMS_CONFIRM_IDENTITY_MINUTES)


def mark_confirmed(request) -> None:
    session = getattr(request, "session", None)
    if session is not None:
        session[SESSION_CONFIRMED_KEY] = timezone.now().timestamp()


def confirmed_until(request) -> datetime | None:
    confirmed_at = request.session.get(SESSION_CONFIRMED_KEY)
    if confirmed_at is None:
        return None
    until = datetime.fromtimestamp(confirmed_at, tz=UTC) + _window()
    return until if until > timezone.now() else None


def is_enabled_for(request) -> bool:
    return is_enabled(F.CONFIRM_SENSITIVE_ACTIONS, request=request)


def is_confirmed(request) -> bool:
    return not is_enabled_for(request) or confirmed_until(request) is not None


def require(request) -> None:
    if not is_confirmed(request):
        raise IdentityConfirmationRequired(
            "This is a sensitive action. Confirm it's you to continue."
        )


def status(request) -> dict:
    return {
        "enabled": is_enabled_for(request),
        "confirmed": is_confirmed(request),
        "confirmed_until": confirmed_until(request),
        "window_minutes": settings.HIMS_CONFIRM_IDENTITY_MINUTES,
        "needs_code": mfa.confirmed_device(request.user) is not None,
    }


def _refuse(request, user) -> None:
    failures = request.session.get(SESSION_FAILURES_KEY, 0) + 1
    record_audit_event(
        action=AuditAction.AUTH_IDENTITY_CONFIRM_FAILED,
        resource_type="user",
        resource_id=user.pk,
        actor=user,
        request=request,
        outcome=AuditEvent.Outcome.FAILURE,
        metadata={"attempt": failures},
    )
    if failures >= MAX_FAILURES:
        record_audit_event(
            action=AuditAction.AUTH_IDENTITY_CONFIRM_LOCKED,
            resource_type="user",
            resource_id=user.pk,
            actor=user,
            request=request,
            outcome=AuditEvent.Outcome.FAILURE,
        )
        logout(getattr(request, "_request", request))  # ends this session
        raise IdentityConfirmationLocked("Too many wrong tries. Please sign in again.")
    request.session[SESSION_FAILURES_KEY] = failures
    raise IdentityNotConfirmed(
        "That was not accepted. Check your password and use the newest code from your app."
    )


def confirm(request, *, password: str, code: str = "") -> None:
    """Check the password, and the authenticator or backup code if the person uses two-factor.
    Five wrong tries end the session: whoever holds it would need the password to get back in."""
    user = request.user
    method = "password"
    accepted = user.check_password(password)
    if accepted and mfa.confirmed_device(user) is not None:
        try:
            with transaction.atomic():  # a backup code is only used up if the password was right
                method = f"password+{mfa._check_code(user, code.strip(), allow_recovery=True)}"
        except mfa.InvalidMfaCode:
            accepted = False
    if not accepted:
        _refuse(request, user)
    request.session.pop(SESSION_FAILURES_KEY, None)
    mark_confirmed(request)
    record_audit_event(
        action=AuditAction.AUTH_IDENTITY_CONFIRMED,
        resource_type="user",
        resource_id=user.pk,
        actor=user,
        request=request,
        metadata={"method": method},
    )


def end(request) -> None:
    """The person is done, or stepping away: ask again next time."""
    request.session.pop(SESSION_CONFIRMED_KEY, None)
