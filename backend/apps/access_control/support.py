"""Supplier support access, the "locked box" (spec 7.2, 7.4; HIMS-IAM-021).

The software supplier (the company that sells HIMS) keeps one support account in each hospital's
deployment. That account holds the "Software supplier support" role: no hospital access at all,
only the right to ask for it.

1. The supplier asks for one role (hospital administrator, or auditor to read the audit log) for
   a few hours, with a reason.
2. The hospital's administrator (``support.access.manage``) approves or refuses it. In an
   emergency the supplier opens it at once instead; by the product owner's decision (2026-11-12)
   the hospital is then not emailed unless ``HIMS_SUPPORT_EMERGENCY_NOTICE`` is on. Emergency
   access is still shown on the Support access page and recorded in the audit log.
3. The access is an ordinary role assignment valid until ``ends_at``, so every permission rule
   applies unchanged and it ends by itself. Either side can end it early.
4. While it lasts, every request the account makes is recorded in the audit log
   (``SupportAccessAuditMiddleware``), which nobody can change or delete (ADR-013).

Rules: the supplier never decides its own request; only one request waits at a time per
account; only the roles in ``ASKABLE_ROLES``; the access never counts as one of the hospital's
administrators (lock-out rule) and is never lent as cover.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import AuditAction, record_audit_event
from apps.notifications.services import send_message
from apps.organizations.dates import hospital_time
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError

from .catalog import P
from .models import Role, RoleAssignment, SupportAccess
from .services import assign_role, close_assignment

Kind = SupportAccess.Kind
State = SupportAccess.State

# The access the supplier may ask for: running the hospital, or reading its audit log. Asked for
# one at a time, so the two stay separate (ADR-013).
ASKABLE_ROLES = ("organization-administrator", "auditor")
SUPPLIER_ROLE = "supplier-support"


def default_hours() -> int:
    return settings.HIMS_SUPPORT_ACCESS_HOURS


def max_hours() -> int:
    return settings.HIMS_SUPPORT_ACCESS_MAX_HOURS


def emergency_notice() -> bool:
    return settings.HIMS_SUPPORT_EMERGENCY_NOTICE


def askable_roles():
    return Role.objects.filter(code__in=ASKABLE_ROLES, is_system=True).order_by("name")


def _when(moment) -> str:
    return hospital_time(moment).strftime("%d %b %Y %H:%M %Z")


def _link() -> str:
    return f"{settings.HIMS_APP_BASE_URL.rstrip('/')}/support-access"


def _manager_emails() -> list[str]:
    now = timezone.now()
    emails = (
        RoleAssignment.objects.filter(
            Q(valid_until__isnull=True) | Q(valid_until__gt=now),
            revoked_at__isnull=True,
            valid_from__lte=now,
            facility__isnull=True,
            user__is_active=True,
            support_access__isnull=True,  # not the supplier's own temporary access
            role__role_permissions__permission__codename=P.SUPPORT_ACCESS_MANAGE,
        )
        .values_list("user__email", flat=True)
        .distinct()
    )
    return sorted(set(emails))


def _send(key: str, values: dict, recipients) -> None:
    recipients = [email for email in recipients if email]
    if recipients:
        send_message(key, to=recipients, values=values)


def _metadata(access: SupportAccess) -> dict:
    return {
        "supplier_id": str(access.requested_by_id),
        "role": access.role.code,
        "kind": access.kind,
        "hours": access.hours,
    }


def _check_request(*, actor, role: Role, reason: str, hours: int) -> None:
    from .selectors import has_permission

    if not has_permission(actor, P.SUPPORT_ACCESS_REQUEST):
        raise ConflictError(
            "Only the software supplier's support account can ask for support access.",
            code="NOT_SUPPLIER",
        )
    if role.code not in ASKABLE_ROLES or not role.is_system:
        raise ConflictError(
            "Ask for the hospital administrator or the auditor role.", code="ROLE_NOT_ASKABLE"
        )
    if not reason.strip():
        raise ConflictError(
            "Give a reason, e.g. 'Check the rota error reported on 12 Nov'.",
            code="REASON_REQUIRED",
        )
    if not 1 <= hours <= max_hours():
        raise ConflictError(
            f"Ask for 1 to {max_hours()} hours. Ask again after that.", code="TOO_LONG"
        )
    if SupportAccess.objects.filter(requested_by=actor, state=State.WAITING).exists():
        raise ConflictError(
            "A request is already waiting for the hospital. Cancel it first to ask again.",
            code="ALREADY_WAITING",
        )


def _give(access: SupportAccess, *, request) -> None:
    """Open the access: a role assignment valid for ``hours`` from now."""
    now = timezone.now()
    access.starts_at = now
    access.ends_at = now + timedelta(hours=access.hours)
    supplier = access.requested_by
    # An earlier period of the same access that simply ran out would block giving it again.
    for leftover in RoleAssignment.objects.select_for_update().filter(
        user=supplier,
        role=access.role,
        facility__isnull=True,
        department__isnull=True,
        revoked_at__isnull=True,
        valid_until__lte=now,
    ):
        close_assignment(
            leftover,
            actor=None,
            reason="The earlier support access had run out; closed so it can be given again.",
            request=request,
            metadata={"expired": True},
        )
    if RoleAssignment.objects.filter(
        user=supplier,
        role=access.role,
        facility__isnull=True,
        department__isnull=True,
        revoked_at__isnull=True,
    ).exists():
        raise ConflictError(
            "The supplier's account already holds this access.", code="ALREADY_HELD"
        )
    # Given by the system on the decision of ``actor`` (or the supplier, in an emergency): the
    # approving administrator may not hold the auditor role, and that is fine (ADR-013).
    access.assignment = assign_role(
        actor=None,
        user=supplier,
        role=access.role,
        valid_until=access.ends_at,
        reason=f"Supplier support access ({access.get_kind_display()}): {access.reason}",
        request=request,
    )
    access.state = State.GRANTED
    supplier.support_access_until = max(
        supplier.support_access_until or access.ends_at, access.ends_at
    )
    supplier.save(update_fields=["support_access_until"])


@transaction.atomic
def request_access(
    *, actor, role: Role, reason: str, hours: int | None = None, emergency=False, request=None
) -> SupportAccess:
    """The supplier asks. A standard request waits for the hospital; an emergency opens now."""
    hours = hours or default_hours()
    reason = reason.strip()
    _check_request(actor=actor, role=role, reason=reason, hours=hours)
    access = SupportAccess.objects.create(
        organization_id=role.organization_id,
        requested_by=actor,
        role=role,
        kind=Kind.EMERGENCY if emergency else Kind.STANDARD,
        reason=reason,
        hours=hours,
    )
    if emergency:
        access.decided_by = actor
        access.decided_at = timezone.now()
        access.decision_note = "Emergency: opened at once by the supplier."
        _give(access, request=request)
        access.save()
        record_audit_event(
            action=AuditAction.SUPPORT_ACCESS_EMERGENCY_OPENED,
            resource_type="support_access",
            resource_id=access.pk,
            actor=actor,
            request=request,
            reason=reason,
            metadata={**_metadata(access), "ends_at": access.ends_at.isoformat()},
        )
        if emergency_notice():
            values = {
                "supplier": actor.display_name,
                "role": access.role.name,
                "until": _when(access.ends_at),
                "reason": reason,
            }
            transaction.on_commit(
                lambda: _send("access.support_emergency_opened", values, _manager_emails())
            )
        return access
    record_audit_event(
        action=AuditAction.SUPPORT_ACCESS_REQUESTED,
        resource_type="support_access",
        resource_id=access.pk,
        actor=actor,
        request=request,
        reason=reason,
        metadata=_metadata(access),
    )
    values = {
        "supplier": actor.display_name,
        "role": access.role.name,
        "hours": str(hours),
        "reason": reason,
        "link": _link(),
    }
    transaction.on_commit(lambda: _send("access.support_requested", values, _manager_emails()))
    return access


def _waiting(access_id, version: int) -> SupportAccess:
    access = lock_for_update(SupportAccess, pk=access_id, expected_version=version)
    if access.state != State.WAITING:
        raise ConflictError("This request has already been answered.", code="ALREADY_DECIDED")
    return access


@transaction.atomic
def approve(*, actor, access_id, version: int, note: str = "", request=None) -> SupportAccess:
    access = _waiting(access_id, version)
    if access.requested_by_id == actor.pk:
        raise ConflictError("The supplier cannot approve its own request.", code="SELF_DECISION")
    if not access.requested_by.is_active:
        raise ConflictError("The supplier's account is switched off.", code="ACCOUNT_INACTIVE")
    access.decided_by = actor
    access.decided_at = timezone.now()
    access.decision_note = note.strip()
    _give(access, request=request)
    bump_version(access)
    access.save()
    record_audit_event(
        action=AuditAction.SUPPORT_ACCESS_APPROVED,
        resource_type="support_access",
        resource_id=access.pk,
        actor=actor,
        request=request,
        reason=access.decision_note,
        metadata={**_metadata(access), "ends_at": access.ends_at.isoformat()},
    )
    values = {
        "role": access.role.name,
        "decision": "approved",
        "decided_by": actor.display_name,
        "details": f"It lasts until {_when(access.ends_at)}.",
    }
    email = access.requested_by.email
    transaction.on_commit(lambda: _send("access.support_decided", values, [email]))
    return access


@transaction.atomic
def refuse(*, actor, access_id, version: int, note: str, request=None) -> SupportAccess:
    access = _waiting(access_id, version)
    note = note.strip()
    if not note:
        raise ConflictError("Say why it is refused.", code="REASON_REQUIRED")
    access.state = State.REFUSED
    access.decided_by = actor
    access.decided_at = timezone.now()
    access.decision_note = note
    bump_version(access)
    access.save()
    record_audit_event(
        action=AuditAction.SUPPORT_ACCESS_REFUSED,
        resource_type="support_access",
        resource_id=access.pk,
        actor=actor,
        request=request,
        reason=note,
        metadata=_metadata(access),
    )
    values = {
        "role": access.role.name,
        "decision": "refused",
        "decided_by": actor.display_name,
        "details": f"Reason: {note}",
    }
    email = access.requested_by.email
    transaction.on_commit(lambda: _send("access.support_decided", values, [email]))
    return access


@transaction.atomic
def cancel(*, actor, access_id, version: int, request=None) -> SupportAccess:
    """The supplier withdraws a request nobody has answered yet."""
    access = _waiting(access_id, version)
    if access.requested_by_id != actor.pk:
        raise ConflictError("Only the supplier who asked can cancel it.", code="NOT_YOURS")
    access.state = State.CANCELLED
    access.ended_at = timezone.now()
    access.ended_by = actor
    bump_version(access)
    access.save()
    record_audit_event(
        action=AuditAction.SUPPORT_ACCESS_CANCELLED,
        resource_type="support_access",
        resource_id=access.pk,
        actor=actor,
        request=request,
        metadata=_metadata(access),
    )
    return access


@transaction.atomic
def end(*, actor, access_id, version: int, reason: str, request=None) -> SupportAccess:
    """End running access now: by the hospital, or by the supplier when the work is done."""
    access = lock_for_update(SupportAccess, pk=access_id, expected_version=version)
    if access.status != SupportAccess.Status.ACTIVE:
        raise ConflictError("This access is not running.", code="NOT_ACTIVE")
    reason = reason.strip()
    if not reason:
        raise ConflictError("Say why it ends early, e.g. 'Work done'.", code="REASON_REQUIRED")
    now = timezone.now()
    access.state = State.ENDED_EARLY
    access.ended_at = now
    access.ended_by = actor
    access.end_reason = reason
    bump_version(access)
    access.save()
    if access.assignment is not None and access.assignment.revoked_at is None:
        close_assignment(
            access.assignment,
            actor=actor,
            reason=f"Supplier support access ended early: {reason}",
            request=request,
            metadata={"support_access_id": str(access.pk)},
        )
    supplier = access.requested_by
    still_running = (
        SupportAccess.objects.filter(requested_by=supplier, state=State.GRANTED, ends_at__gt=now)
        .exclude(pk=access.pk)
        .order_by("-ends_at")
        .values_list("ends_at", flat=True)
        .first()
    )
    supplier.support_access_until = still_running
    supplier.save(update_fields=["support_access_until"])
    record_audit_event(
        action=AuditAction.SUPPORT_ACCESS_ENDED,
        resource_type="support_access",
        resource_id=access.pk,
        actor=actor,
        request=request,
        reason=reason,
        metadata=_metadata(access),
    )
    return access


def is_supplier_on_support(user) -> bool:
    """True while the account works under support access (no database query)."""
    until = getattr(user, "support_access_until", None)
    return until is not None and until > timezone.now()
