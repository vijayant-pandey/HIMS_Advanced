"""Cover arrangements: delegated access (spec 4.4 "delegated access", 13.2; HIMS-IAM-017).

An administrator arranges for one person (the delegate) to work, for a limited time, with some
or all of another person's access (the delegator), e.g. while the delegator is on leave.

How it works: each chosen role assignment of the delegator is *copied* to the delegate as an
ordinary ``RoleAssignment`` that is valid only for the cover period and points back to the
delegation and to the original. So scope, expiry, revocation, the Access page, access reviews
and the audit log all work unchanged, and the permission check itself is not touched.

Rules:
* time-limited (at most ``HIMS_DELEGATION_MAX_DAYS``, default 30) with a reason;
* the same safeguards as giving access by hand: nobody arranges cover for themselves as the
  covering person, nobody hands out permissions they do not hold, only active facilities;
* only a person's *own* access can be lent: lent access cannot be lent on (no chains);
* roles holding ``audit.view`` are never lent (auditors stay independent, ADR-013);
* lent access never counts as one of the hospital's administrators (lock-out rule);
* it ends early with a reason, when the original access is removed, or when either person's
  account is switched off. Otherwise it simply runs out.

Clinical delegation (e.g. a consultant's patients) needs clinical governance sign-off and is
not part of this (spec 26.4).
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import AuditAction, record_audit_event
from apps.notifications.services import send_email
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError

from .catalog import P
from .models import AccessDelegation, RoleAssignment
from .reviews import scope_label
from .services import assign_role, close_assignment

logger = logging.getLogger(__name__)

Status = AccessDelegation.Status

# Roles holding any of these are never lent (auditors must stay independent of the people they
# audit; ADR-013 separation of duties).
NOT_DELEGABLE_PERMISSIONS = frozenset({P.AUDIT_VIEW})
# A start time this far in the past is still accepted (the form was open for a while).
START_GRACE = timedelta(minutes=5)


def max_days() -> int:
    return settings.HIMS_DELEGATION_MAX_DAYS


def own_current_assignments(user):
    """The person's own access right now (not access lent to them)."""
    now = timezone.now()
    return (
        RoleAssignment.objects.filter(
            user=user, revoked_at__isnull=True, valid_from__lte=now, delegation__isnull=True
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
        .select_related("role", "facility", "department")
        .order_by("role__name")
    )


def why_not_delegable(assignment: RoleAssignment) -> str:
    codes = set(assignment.role.permissions.values_list("codename", flat=True))
    if codes & NOT_DELEGABLE_PERMISSIONS:
        return "Auditor access is never lent: auditors must stay independent."
    return ""


def delegable_assignments(user) -> tuple[list[RoleAssignment], list[tuple[RoleAssignment, str]]]:
    """(can be lent, cannot be lent with the reason) for the person's current access."""
    lendable, refused = [], []
    for assignment in own_current_assignments(user):
        why = why_not_delegable(assignment)
        if why:
            refused.append((assignment, why))
        else:
            lendable.append(assignment)
    return lendable, refused


def _validate_people_and_period(*, actor, delegator, delegate, starts_at, ends_at, reason):
    if delegator.pk == delegate.pk:
        raise ConflictError("Choose two different people.", code="SAME_PERSON")
    if actor is not None and delegate.pk == actor.pk:
        raise ConflictError(
            "You cannot arrange cover that gives yourself access; ask another administrator.",
            code="SELF_ASSIGNMENT",
        )
    for person in (delegator, delegate):
        if not person.is_active:
            raise ConflictError(
                f"{person.display_name}'s account is switched off.", code="ACCOUNT_INACTIVE"
            )
    if not reason.strip():
        raise ConflictError("Give a reason, e.g. 'Annual leave'.", code="REASON_REQUIRED")
    now = timezone.now()
    if starts_at < now - START_GRACE:
        raise ConflictError("The cover cannot start in the past.", code="START_IN_PAST")
    if ends_at <= starts_at or ends_at <= now:
        raise ConflictError(
            "The end must be after the start and in the future.", code="INVALID_PERIOD"
        )
    if ends_at - starts_at > timedelta(days=max_days()):
        raise ConflictError(
            f"Cover can last at most {max_days()} days. Arrange a new period after that.",
            code="TOO_LONG",
        )
    overlapping = AccessDelegation.objects.filter(
        delegator=delegator,
        delegate=delegate,
        ended_at__isnull=True,
        starts_at__lt=ends_at,
        ends_at__gt=starts_at,
    )
    if overlapping.exists():
        raise ConflictError(
            f"{delegate.display_name} already covers for {delegator.display_name} in this "
            "period. End that cover first or choose other dates.",
            code="OVERLAPPING",
        )


def validate_delegation(*, actor, delegator, delegate, starts_at, ends_at, reason) -> None:
    """The checks that need no database change (also used by the admin console form)."""
    _validate_people_and_period(
        actor=actor,
        delegator=delegator,
        delegate=delegate,
        starts_at=starts_at or timezone.now(),
        ends_at=ends_at,
        reason=reason,
    )
    if not delegable_assignments(delegator)[0]:
        raise ConflictError(
            f"{delegator.display_name} has no access that can be lent.", code="NOTHING_TO_DELEGATE"
        )


def _close_expired_leftover(*, actor, delegate, source: RoleAssignment, request) -> None:
    """An earlier access period that ran out (never revoked) would block giving the same role
    again; close it first (recorded like any revocation)."""
    leftovers = RoleAssignment.objects.select_for_update().filter(
        user=delegate,
        role_id=source.role_id,
        facility_id=source.facility_id,
        department_id=source.department_id,
        revoked_at__isnull=True,
        valid_until__lte=timezone.now(),
    )
    for leftover in leftovers:
        close_assignment(
            leftover,
            actor=actor,
            reason="The access period had already ended; closed so it can be given again.",
            request=request,
            metadata={"expired": True},
        )


def _already_holds(delegate, source: RoleAssignment) -> bool:
    return RoleAssignment.objects.filter(
        user=delegate,
        role_id=source.role_id,
        facility_id=source.facility_id,
        department_id=source.department_id,
        revoked_at__isnull=True,
    ).exists()


@transaction.atomic
def create_delegation(
    *,
    actor,
    delegator,
    delegate,
    ends_at,
    reason: str,
    starts_at=None,
    assignment_ids=None,
    request=None,
) -> tuple[AccessDelegation, list[dict]]:
    """Arrange cover. ``assignment_ids`` limits it to some of the delegator's access (default:
    everything that can be lent). Returns the arrangement and the roles skipped because the
    covering person already has them."""
    starts_at = starts_at or timezone.now()
    reason = reason.strip()
    _validate_people_and_period(
        actor=actor,
        delegator=delegator,
        delegate=delegate,
        starts_at=starts_at,
        ends_at=ends_at,
        reason=reason,
    )
    lendable, refused = delegable_assignments(delegator)
    if assignment_ids is not None:
        wanted = {str(pk) for pk in assignment_ids}
        if not wanted:
            raise ConflictError("Choose at least one role to lend.", code="NOTHING_TO_DELEGATE")
        known = {str(a.pk) for a in lendable}
        if wanted - known:
            refused_ids = {str(a.pk) for a, _ in refused}
            why = (
                refused[0][1]
                if wanted & refused_ids
                else "Only the covered person's own current access can be lent."
            )
            raise ConflictError(why, code="NOT_DELEGABLE")
        lendable = [a for a in lendable if str(a.pk) in wanted]
    if not lendable:
        raise ConflictError(
            f"{delegator.display_name} has no access that can be lent.", code="NOTHING_TO_DELEGATE"
        )

    delegation = AccessDelegation.objects.create(
        organization_id=lendable[0].organization_id,
        delegator=delegator,
        delegate=delegate,
        starts_at=starts_at,
        ends_at=ends_at,
        reason=reason,
        created_by=actor,
    )
    lent, skipped = [], []
    for source in lendable:
        _close_expired_leftover(actor=actor, delegate=delegate, source=source, request=request)
        if _already_holds(delegate, source):
            skipped.append(
                {
                    "role_name": source.role.name,
                    "scope": scope_label(source),
                    "why": f"{delegate.display_name} already has this access.",
                }
            )
            continue
        valid_until = ends_at
        if source.valid_until is not None and source.valid_until < valid_until:
            valid_until = source.valid_until  # never longer than the original
        if valid_until <= starts_at:
            skipped.append(
                {
                    "role_name": source.role.name,
                    "scope": scope_label(source),
                    "why": "The covered person's own access ends before the cover starts.",
                }
            )
            continue
        assign_role(
            actor=actor,
            user=delegate,
            role=source.role,
            facility=source.facility,
            department=source.department,
            valid_from=starts_at,
            valid_until=valid_until,
            reason=f"Cover for {delegator.display_name}: {reason}",
            request=request,
            delegation=delegation,
            delegated_from=source,
        )
        lent.append({"role_name": source.role.name, "scope": scope_label(source)})
    if not lent:
        raise ConflictError(
            f"{delegate.display_name} already has all of this access; no cover is needed.",
            code="NOTHING_TO_DELEGATE",
        )
    record_audit_event(
        action=AuditAction.ACCESS_DELEGATION_CREATED,
        resource_type="access_delegation",
        resource_id=delegation.pk,
        actor=actor,
        request=request,
        reason=reason,
        metadata={
            "delegator_id": str(delegator.pk),
            "delegate_id": str(delegate.pk),
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
            "roles": lent,
            "skipped": skipped,
        },
    )
    transaction.on_commit(lambda: _notify_created(delegation, lent))
    return delegation, skipped


@transaction.atomic
def end_delegation(
    *, actor, delegation_id, version: int, reason: str, request=None
) -> AccessDelegation:
    """End cover now: every lent copy is removed at once (also ones not started yet)."""
    delegation = lock_for_update(AccessDelegation, pk=delegation_id, expected_version=version)
    if delegation.status in (Status.ENDED_EARLY, Status.FINISHED):
        raise ConflictError("This cover has already ended.", code="ALREADY_ENDED")
    reason = reason.strip()
    if not reason:
        raise ConflictError("Give a reason for ending the cover early.", code="REASON_REQUIRED")
    delegation.ended_at = timezone.now()
    delegation.ended_by = actor
    delegation.end_reason = reason
    bump_version(delegation)
    delegation.save()
    for copy in delegation.assignments.select_for_update().filter(revoked_at__isnull=True):
        close_assignment(
            copy,
            actor=actor,
            reason=f"Cover ended early: {reason}",
            request=request,
            metadata={"delegation_id": str(delegation.pk)},
        )
    record_audit_event(
        action=AuditAction.ACCESS_DELEGATION_ENDED,
        resource_type="access_delegation",
        resource_id=delegation.pk,
        actor=actor,
        request=request,
        reason=reason,
        metadata={
            "delegator_id": str(delegation.delegator_id),
            "delegate_id": str(delegation.delegate_id),
        },
    )
    transaction.on_commit(lambda: _notify_ended(delegation))
    return delegation


def open_delegations_of(user):
    """Cover not ended yet in which the person covers or is covered."""
    return AccessDelegation.objects.filter(
        Q(delegator=user) | Q(delegate=user), ended_at__isnull=True, ends_at__gt=timezone.now()
    )


def end_delegations_for_user(user) -> int:
    """When an account is switched off (leaving, suspension), its cover arrangements end too:
    nobody keeps working with a former colleague's access. Returns how many ended."""
    ended = 0
    for delegation in open_delegations_of(user):
        end_delegation(
            actor=None,
            delegation_id=delegation.pk,
            version=delegation.version,
            reason=f"{user.display_name}'s account was switched off.",
        )
        ended += 1
    return ended


# --- Emails (no clinical data; dates and access only) ------------------------------------


def _period(delegation: AccessDelegation) -> str:
    zone = timezone.get_current_timezone()
    start = timezone.localtime(delegation.starts_at, zone).strftime("%d %b %Y %H:%M")
    end = timezone.localtime(delegation.ends_at, zone).strftime("%d %b %Y %H:%M")
    return f"from {start} to {end}"


def _send(subject: str, body: str, *emails: str) -> None:
    recipients = [e for e in emails if e]
    if recipients:
        send_email(
            subject=subject,
            body=body,
            to=recipients,
            category="access",
            template="access.cover",
        )


def _notify_created(delegation: AccessDelegation, lent: list[dict]) -> None:
    roles = "\n".join(f"- {r['role_name']} ({r['scope']})" for r in lent)
    delegator, delegate = delegation.delegator, delegation.delegate
    _send(
        f"HIMS: you are covering for {delegator.display_name}",
        f"You will work with {delegator.display_name}'s access {_period(delegation)}.\n\n"
        f"Reason: {delegation.reason}\n\nAccess lent to you:\n{roles}\n\n"
        "Everything you do is recorded under your own name. The access ends by itself.\n",
        delegate.email,
    )
    _send(
        f"HIMS: {delegate.display_name} is covering for you",
        f"{delegate.display_name} will work with your access {_period(delegation)}.\n\n"
        f"Reason: {delegation.reason}\n\nAccess lent:\n{roles}\n\n"
        "If you did not expect this, tell your hospital administrator.\n",
        delegator.email,
    )


def _notify_ended(delegation: AccessDelegation) -> None:
    delegator, delegate = delegation.delegator, delegation.delegate
    body = (
        f"The cover by {delegate.display_name} for {delegator.display_name} ended early.\n\n"
        f"Reason: {delegation.end_reason}\n"
    )
    _send("HIMS: cover arrangement ended", body, delegate.email, delegator.email)
