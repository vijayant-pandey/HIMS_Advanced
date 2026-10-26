"""Forgotten-password recovery (HIMS-IAM-004; spec 13.1, 13.5, 29.1).

Flow: the person enters their email -> the same "check your email" answer is always returned ->
if an activated account exists, a reset row is created and ``identity.password_reset.requested``
is published -> the email with a single-use link is sent -> the person chooses a new password ->
every existing session is signed out and a "password changed" notice is emailed.

Security properties:
* No account enumeration: unknown, inactive and not-yet-activated emails get the same response
  and send nothing.
* Links expire quickly (HIMS_PASSWORD_RESET_TTL_MINUTES), are single use, and a newer request
  revokes the older link. At most HIMS_PASSWORD_RESET_MAX_PER_HOUR emails per account per hour.
* Changing the password changes Django's session auth hash, so every other session of the user
  stops working on its next request (a stolen session cannot outlive a reset).
* Tokens are never stored and travel only in the URL fragment.
"""

import hashlib
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction, record_audit_event
from common.exceptions import DomainError
from common.outbox.services import publish_event

from .models import PasswordReset, User
from .tokens import app_link, make_link_token, read_link_token

TOKEN_SALT = "hims.identity.password-reset"  # noqa: S105 - namespace for signing, not a secret
RESET_REQUESTED_EVENT = "identity.password_reset.requested"
PASSWORD_CHANGED_EVENT = "identity.password.changed"  # noqa: S105 - event name
INVALID_LINK_MESSAGE = (
    "This password reset link is invalid, has expired or was already used. "
    "Request a new one from the sign-in page."
)


class PasswordResetInvalid(DomainError):
    status_code = 400
    code = "PASSWORD_RESET_INVALID"
    title = "Password reset link is not valid"


def make_token(reset: PasswordReset) -> str:
    return make_link_token(reset.pk, salt=TOKEN_SALT)


def reset_link(reset: PasswordReset) -> str:
    return app_link("reset-password", make_token(reset))


def _email_fingerprint(email: str) -> str:
    """Lets investigators correlate repeated attempts without storing unknown addresses."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]


def request_password_reset(*, email: str, request=None) -> None:
    """Always returns normally; whether an email is sent depends on the account (no enumeration)."""
    user = User.objects.filter(email__iexact=email.strip()).first()
    eligible = user is not None and user.is_active and user.has_usable_password()
    if eligible:
        recent = PasswordReset.objects.filter(
            user=user, created_at__gte=timezone.now() - timedelta(hours=1)
        ).count()
        eligible = recent < settings.HIMS_PASSWORD_RESET_MAX_PER_HOUR

    if not eligible:
        record_audit_event(
            action=AuditAction.PASSWORD_RESET_REQUESTED,
            resource_type="user",
            resource_id=user.pk if user else "",
            request=request,
            outcome=AuditEvent.Outcome.FAILURE,
            metadata={"email_fingerprint": _email_fingerprint(email), "email_sent": False},
        )
        return
    _issue_reset(user=user, request=request)


@transaction.atomic
def _issue_reset(*, user: User, request=None) -> PasswordReset:
    now = timezone.now()
    PasswordReset.objects.select_for_update().filter(
        user=user, used_at__isnull=True, revoked_at__isnull=True
    ).update(revoked_at=now)
    reset = PasswordReset.objects.create(
        user=user, expires_at=now + timedelta(minutes=settings.HIMS_PASSWORD_RESET_TTL_MINUTES)
    )
    record_audit_event(
        action=AuditAction.PASSWORD_RESET_REQUESTED,
        resource_type="user",
        resource_id=user.pk,
        request=request,
        metadata={"reset_id": str(reset.pk), "email_sent": True},
    )
    publish_event(
        event_type=RESET_REQUESTED_EVENT,
        aggregate_type="user",
        aggregate_id=user.pk,
        payload={"reset_id": str(reset.pk)},
    )
    return reset


def _reset_for_token(token: str, *, lock: bool = False) -> PasswordReset:
    reset_id = read_link_token(token, salt=TOKEN_SALT)
    if reset_id is None:
        raise PasswordResetInvalid(INVALID_LINK_MESSAGE)
    queryset = PasswordReset.objects.select_related("user")
    if lock:
        queryset = queryset.select_for_update()
    reset = queryset.filter(pk=reset_id).first()
    if reset is None or reset.status != "open" or not reset.user.is_active:
        raise PasswordResetInvalid(INVALID_LINK_MESSAGE)
    return reset


def inspect_reset(token: str) -> PasswordReset:
    return _reset_for_token(token)


def complete_password_reset(*, token: str, password: str, request=None) -> User:
    try:
        return _complete(token=token, password=password, request=request)
    except PasswordResetInvalid:
        # Recorded after the failed transaction has rolled back, so the record is kept.
        record_audit_event(
            action=AuditAction.PASSWORD_RESET_REJECTED,
            resource_type="user_password_reset",
            request=request,
            outcome=AuditEvent.Outcome.FAILURE,
        )
        raise


@transaction.atomic
def _complete(*, token: str, password: str, request=None) -> User:
    reset = _reset_for_token(token, lock=True)
    user = reset.user
    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise ValidationError({"password": exc.messages}) from exc

    now = timezone.now()
    user.set_password(password)  # new session auth hash: all other sessions end
    user.password_changed_at = now
    user.save(update_fields=["password", "password_changed_at"])
    reset.used_at = now
    reset.save(update_fields=["used_at"])
    record_audit_event(
        action=AuditAction.PASSWORD_RESET_COMPLETED,
        resource_type="user",
        resource_id=user.pk,
        actor=user,
        request=request,
        metadata={"reset_id": str(reset.pk)},
    )
    publish_event(
        event_type=PASSWORD_CHANGED_EVENT,
        aggregate_type="user",
        aggregate_id=user.pk,
        payload={"user_id": str(user.pk)},
    )
    return user


def _hospital_name() -> str:
    from apps.organizations.models import Organization

    organization = Organization.objects.only("display_name").first()
    return organization.display_name if organization else "HIMS"


def send_reset_email(reset: PasswordReset) -> None:
    hospital = _hospital_name()
    body = (
        f"Hello {reset.user.display_name},\n\n"
        f"We received a request to reset the password of your {hospital} HIMS account.\n"
        f"Open this link to choose a new password:\n\n"
        f"{reset_link(reset)}\n\n"
        f"The link can be used once and expires in "
        f"{settings.HIMS_PASSWORD_RESET_TTL_MINUTES} minutes.\n"
        f"If you did not ask for this, you can ignore this email; your password stays the same.\n"
    )
    send_mail(
        subject=f"Reset your {hospital} HIMS password",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[reset.user.email],
    )


def send_password_changed_notice(user: User) -> None:
    hospital = _hospital_name()
    body = (
        f"Hello {user.display_name},\n\n"
        f"The password of your {hospital} HIMS account was just changed, and all devices "
        f"that were signed in have been signed out.\n\n"
        f"If you did not do this, contact your hospital administrator immediately.\n"
    )
    send_mail(
        subject=f"Your {hospital} HIMS password was changed",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )
