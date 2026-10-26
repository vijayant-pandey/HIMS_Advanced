"""Staff invitation and account activation (HIMS-IAM-003; spec 4.4, 13.1, 29.1).

Flow: a staff member is created with an email -> ``staff.member.created`` event -> an invitation
is issued -> ``identity.invitation.issued`` event -> the email with the activation link is sent.
Administrators can also (re)send an invitation, which revokes any earlier open one.

Security properties:
* The link token is a signed reference to the invitation, never stored in the database.
* The token travels in the URL **fragment** (``#token=...``), which browsers never send to
  servers, so it stays out of access logs and Referer headers (spec 29.1). The SPA posts it in
  the request body.
* Invalid, expired, used and revoked links all return the same error (no enumeration).
* Single use; inactive (suspended/terminated) users cannot activate.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction, record_audit_event
from common.exceptions import ConflictError, DomainError
from common.outbox.services import publish_event

from .models import Invitation, User
from .tokens import app_link, make_link_token, read_link_token

TOKEN_SALT = "hims.identity.invitation"  # noqa: S105 - namespace for signing, not a secret
INVITATION_ISSUED_EVENT = "identity.invitation.issued"
INVALID_LINK_MESSAGE = (
    "This invitation link is invalid, has expired or was already used. "
    "Ask your administrator to send a new invitation."
)


class InvitationInvalid(DomainError):
    status_code = 400
    code = "INVITATION_INVALID"
    title = "Invitation link is not valid"


def make_token(invitation: Invitation) -> str:
    return make_link_token(invitation.pk, salt=TOKEN_SALT)


def activation_link(invitation: Invitation) -> str:
    return app_link("activate", make_token(invitation))


def _invitation_for_token(token: str, *, lock: bool = False) -> Invitation:
    invitation_id = read_link_token(token, salt=TOKEN_SALT)
    if invitation_id is None:
        raise InvitationInvalid(INVALID_LINK_MESSAGE)
    queryset = Invitation.objects.select_related("user")
    if lock:
        queryset = queryset.select_for_update()
    invitation = queryset.filter(pk=invitation_id).first()
    if invitation is None or invitation.status != "open" or not invitation.user.is_active:
        raise InvitationInvalid(INVALID_LINK_MESSAGE)
    return invitation


@transaction.atomic
def issue_invitation(*, user: User, actor=None, request=None) -> Invitation:
    """Create a fresh invitation (revoking any open one) and queue the email."""
    if not user.is_active:
        raise ConflictError("This account is not active.", code="USER_INACTIVE")
    if user.has_usable_password():
        raise ConflictError("This account is already activated.", code="ALREADY_ACTIVATED")

    now = timezone.now()
    Invitation.objects.select_for_update().filter(
        user=user, accepted_at__isnull=True, revoked_at__isnull=True
    ).update(revoked_at=now)
    invitation = Invitation.objects.create(
        user=user,
        created_by=actor,
        expires_at=now + timedelta(hours=settings.HIMS_INVITATION_TTL_HOURS),
    )
    record_audit_event(
        action=AuditAction.USER_INVITATION_ISSUED,
        resource_type="user",
        resource_id=user.pk,
        actor=actor,
        request=request,
        metadata={"invitation_id": str(invitation.pk), "expires_at": invitation.expires_at},
    )
    # The payload carries only the invitation ID; the token is derived when the email is sent.
    publish_event(
        event_type=INVITATION_ISSUED_EVENT,
        aggregate_type="user",
        aggregate_id=user.pk,
        payload={"invitation_id": str(invitation.pk)},
    )
    return invitation


def send_invitation_email(invitation: Invitation) -> None:
    from apps.organizations.models import Organization

    organization = Organization.objects.only("display_name").first()
    hospital = organization.display_name if organization else "HIMS"
    expires = timezone.localtime(invitation.expires_at).strftime("%d %b %Y, %H:%M %Z")
    body = (
        f"Hello {invitation.user.display_name},\n\n"
        f"You have been invited to use the {hospital} hospital system (HIMS).\n"
        f"Open this link to choose your password and activate your account:\n\n"
        f"{activation_link(invitation)}\n\n"
        f"The link can be used once and expires on {expires}.\n"
        f"If you were not expecting this email, you can ignore it.\n"
    )
    send_mail(
        subject=f"Activate your {hospital} HIMS account",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.user.email],
    )


def inspect_invitation(token: str) -> Invitation:
    """Validate a link so the activation page can greet the user; changes nothing."""
    return _invitation_for_token(token)


def accept_invitation(*, token: str, password: str, request=None) -> User:
    try:
        return _accept(token=token, password=password, request=request)
    except InvitationInvalid:
        # Recorded after the failed transaction has rolled back, so the record is kept.
        record_audit_event(
            action=AuditAction.USER_INVITATION_REJECTED,
            resource_type="user_invitation",
            request=request,
            outcome=AuditEvent.Outcome.FAILURE,
        )
        raise


@transaction.atomic
def _accept(*, token: str, password: str, request=None) -> User:
    invitation = _invitation_for_token(token, lock=True)
    user = invitation.user
    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise ValidationError({"password": exc.messages}) from exc

    now = timezone.now()
    user.set_password(password)
    user.password_changed_at = now
    user.save(update_fields=["password", "password_changed_at"])
    invitation.accepted_at = now
    invitation.save(update_fields=["accepted_at"])
    record_audit_event(
        action=AuditAction.USER_INVITATION_ACCEPTED,
        resource_type="user",
        resource_id=user.pk,
        actor=user,
        request=request,
        metadata={"invitation_id": str(invitation.pk)},
    )
    return user
