"""Sign-in accounts, including people who are not staff (HIMS-IAM-015).

Most accounts belong to staff and follow their employment status (apps.staff). Some do not:
the first administrator and auditor created at provisioning, external auditors, IT support.
This module manages those, and holds the rule that the hospital can never lock itself out.
"""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import AuditAction, record_audit_event
from common.exceptions import ConflictError

from .models import User

ADMIN_ROLE = "organization-administrator"


def active_administrators():
    """Users who can run the whole hospital right now (active, organization-wide admin role)."""
    from apps.access_control.models import RoleAssignment

    now = timezone.now()
    holders = RoleAssignment.objects.filter(
        Q(valid_until__isnull=True) | Q(valid_until__gt=now),
        role__code=ADMIN_ROLE,
        role__is_system=True,
        facility__isnull=True,
        revoked_at__isnull=True,
        valid_from__lte=now,
    ).values("user_id")
    return User.objects.filter(is_active=True, pk__in=holders)


def ensure_not_last_administrator(user: User) -> None:
    """Refuse to switch off the only remaining hospital administrator (no lock-out)."""
    if not active_administrators().filter(pk=user.pk).exists():
        return
    if not active_administrators().exclude(pk=user.pk).exists():
        raise ConflictError(
            "This is the last active hospital administrator. Give another person the "
            "Organization administrator role first, so the hospital is never locked out.",
            code="LAST_ADMINISTRATOR",
        )


@transaction.atomic
def create_account(*, actor, email: str, display_name: str, reason: str, request=None) -> User:
    """An account for someone who is not on the staff list (e.g. an external auditor). It gets
    no access until a role is given, and signs in only after accepting the emailed invitation."""
    from .invitations import issue_invitation
    from .services import create_user

    user = create_user(
        email=email.strip().lower(), display_name=display_name.strip(), actor=actor, request=request
    )
    record_audit_event(
        action=AuditAction.ACCOUNT_CREATED,
        resource_type="user",
        resource_id=user.pk,
        actor=actor,
        request=request,
        reason=reason,
        metadata={"staff_record": False},
    )
    issue_invitation(user=user, actor=actor, request=request)
    return user


@transaction.atomic
def set_account_active(*, actor, user_id, active: bool, reason: str, request=None) -> User:
    """Switch an account off (signs the person out everywhere) or back on."""
    user = User.objects.select_for_update().get(pk=user_id)
    if actor is not None and user.pk == actor.pk:
        raise ConflictError(
            "You cannot switch your own account off or on. Ask another administrator.",
            code="SELF_ACCOUNT_CHANGE",
        )
    if getattr(user, "staff_member", None) is not None:
        raise ConflictError(
            "This account belongs to a staff member: change their employment status on the "
            "Staff page instead (suspended or terminated staff cannot sign in).",
            code="ACCOUNT_FOLLOWS_EMPLOYMENT",
        )
    if user.is_active == active:
        return user
    if not active:
        ensure_not_last_administrator(user)
    user.is_active = active
    user.save(update_fields=["is_active"])  # switching off ends every session (sessions.py)
    record_audit_event(
        action=AuditAction.ACCOUNT_REACTIVATED if active else AuditAction.ACCOUNT_DEACTIVATED,
        resource_type="user",
        resource_id=user.pk,
        actor=actor,
        request=request,
        reason=reason,
    )
    return user
