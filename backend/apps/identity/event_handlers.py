"""Outbox consumers for the identity domain (ADR-012). Handlers must be safe to re-run."""

from common.outbox.registry import event_handler

from .invitations import INVITATION_ISSUED_EVENT, issue_invitation, send_invitation_email
from .models import Invitation, PasswordReset, User
from .password_reset import (
    PASSWORD_CHANGED_EVENT,
    RESET_REQUESTED_EVENT,
    send_password_changed_notice,
    send_reset_email,
)


@event_handler("staff.member.created")
def invite_new_staff_login(event) -> None:
    """A new staff member with a login gets an invitation automatically."""
    user_id = event.payload.get("user_id")
    if not user_id:
        return
    user = User.objects.filter(pk=user_id).first()
    if user is None or not user.is_active or user.has_usable_password():
        return
    issue_invitation(user=user)


@event_handler(INVITATION_ISSUED_EVENT)
def email_invitation(event) -> None:
    invitation = (
        Invitation.objects.select_related("user")
        .filter(pk=event.payload.get("invitation_id"))
        .first()
    )
    # A newer invitation may have replaced this one before the email went out.
    if invitation is None or invitation.status != "open":
        return
    send_invitation_email(invitation)


@event_handler(RESET_REQUESTED_EVENT)
def email_password_reset(event) -> None:
    reset = (
        PasswordReset.objects.select_related("user")
        .filter(pk=event.payload.get("reset_id"))
        .first()
    )
    # A newer request may have replaced this one before the email went out.
    if reset is None or reset.status != "open":
        return
    send_reset_email(reset)


@event_handler(PASSWORD_CHANGED_EVENT)
def email_password_changed_notice(event) -> None:
    user = User.objects.filter(pk=event.payload.get("user_id")).first()
    if user is not None:
        send_password_changed_notice(user)
