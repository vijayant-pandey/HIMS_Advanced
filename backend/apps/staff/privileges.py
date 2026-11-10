"""Clinical privileges: what a person may perform, kept by the hospital (HIMS-STAFF-016; spec 4.3).

Spec 4.3 keeps a doctor's degree, designation, specialty and permission to perform a procedure as
separate concepts, so a privilege is its own record. The hospital writes the list and decides who
holds what; HIMS holds no clinical rules of its own (CLIN, 2026-11-08: fine for now).

Nothing checks a privilege yet, because clinical actions arrive in Phase 2. They will ask
``holds_privilege``. Grants are never edited or deleted: one is ended with a reason, and a change
is a new grant, so the record shows who could do what on any past day.
"""

from datetime import date

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import AuditAction, record_audit_event, snapshot
from apps.organizations.dates import hospital_today
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError

from .models import ClinicalPrivilege, StaffDepartmentAssignment, StaffMember, StaffPrivilege

GRANT_FIELDS = ["staff_id", "privilege_id", "department_id", "valid_from", "valid_until", "note"]
_WORKING = (StaffMember.EmploymentStatus.ACTIVE, StaffMember.EmploymentStatus.ON_LEAVE)


def check_grant(
    *,
    actor,
    staff: StaffMember,
    privilege: ClinicalPrivilege,
    department,
    valid_from: date,
    valid_until: date | None,
) -> None:
    """Every rule for a new grant; raises ConflictError with the reason."""
    if staff.user_id and staff.user_id == getattr(actor, "pk", None):
        raise ConflictError(
            "You cannot give yourself a clinical privilege; someone else has to.",
            code="SELF_GRANT",
        )
    if staff.employment_status not in _WORKING:
        raise ConflictError(f"{staff} is not working here.", code="NOT_WORKING")
    if not privilege.is_active:
        raise ConflictError(f"{privilege.name} is switched off.", code="PRIVILEGE_OFF")
    if valid_until is not None and valid_until < valid_from:
        raise ConflictError("The end date cannot be before the start.", code="INVALID_DATES")
    if department is not None and not (
        StaffDepartmentAssignment.objects.filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=valid_from),
            staff=staff,
            department=department,
            valid_from__lte=valid_until or valid_from,
        ).exists()
    ):
        raise ConflictError(f"{staff} is not posted in {department.name}.", code="NOT_POSTED")
    if StaffPrivilege.objects.filter(
        staff=staff,
        privilege=privilege,
        department=department,
        status=StaffPrivilege.Status.ACTIVE,
    ).exists():
        raise ConflictError(
            f"{staff} already holds {privilege.name} here. End it first to change it.",
            code="ALREADY_HELD",
        )


@transaction.atomic
def grant_privilege(
    *,
    actor,
    staff: StaffMember,
    privilege: ClinicalPrivilege,
    department=None,
    valid_from: date | None = None,
    valid_until: date | None = None,
    note: str = "",
    request=None,
) -> StaffPrivilege:
    valid_from = valid_from or hospital_today()
    check_grant(
        actor=actor,
        staff=staff,
        privilege=privilege,
        department=department,
        valid_from=valid_from,
        valid_until=valid_until,
    )
    try:
        with transaction.atomic():
            grant = StaffPrivilege.objects.create(
                organization_id=staff.organization_id,
                staff=staff,
                privilege=privilege,
                department=department,
                valid_from=valid_from,
                valid_until=valid_until,
                note=note.strip(),
                granted_by=actor,
            )
    except IntegrityError:  # two people granting at the same moment
        raise ConflictError(
            f"{staff} already holds {privilege.name} here.", code="ALREADY_HELD"
        ) from None
    record_audit_event(
        action=AuditAction.STAFF_PRIVILEGE_GRANTED,
        resource_type="staff_privilege",
        resource_id=grant.pk,
        actor=actor,
        request=request,
        changes={"after": snapshot(grant, GRANT_FIELDS)},
        metadata={"privilege": privilege.code},
    )
    return grant


def _end(grant: StaffPrivilege, *, actor, reason: str, request=None) -> None:
    grant.status = StaffPrivilege.Status.ENDED
    grant.ended_at = timezone.now()
    grant.ended_by = actor
    grant.end_reason = reason[:255]
    bump_version(grant)
    grant.save()
    record_audit_event(
        action=AuditAction.STAFF_PRIVILEGE_ENDED,
        resource_type="staff_privilege",
        resource_id=grant.pk,
        actor=actor,
        request=request,
        reason=reason,
        metadata={"privilege": grant.privilege.code, "staff_member_id": str(grant.staff_id)},
    )


@transaction.atomic
def end_privilege(*, actor, grant_id, version: int, reason: str, request=None) -> StaffPrivilege:
    grant = lock_for_update(StaffPrivilege, pk=grant_id, expected_version=version)
    if grant.status != StaffPrivilege.Status.ACTIVE:
        raise ConflictError("This privilege has already ended.", code="ALREADY_ENDED")
    if not reason.strip():
        raise ConflictError("Give a reason.", code="REASON_REQUIRED")
    _end(grant, actor=actor, reason=reason.strip(), request=request)
    return grant


@transaction.atomic
def end_all_privileges(staff: StaffMember, *, reason: str) -> int:
    """Employment ended: nothing stays held. Recorded with no actor and the reason."""
    grants = StaffPrivilege.objects.select_for_update().filter(
        staff=staff, status=StaffPrivilege.Status.ACTIVE
    )
    count = 0
    for grant in grants:
        _end(grant, actor=None, reason=reason)
        count += 1
    return count


def holds_privilege(
    staff: StaffMember, code: str, *, department=None, on_date: date | None = None
) -> bool:
    """For the clinical actions of Phase 2: may this person do this, here, on this day? A grant
    with no department applies everywhere the person works. Someone suspended or on long leave
    holds nothing."""
    if staff.employment_status != StaffMember.EmploymentStatus.ACTIVE:
        return False
    day = on_date or hospital_today()
    grants = StaffPrivilege.objects.filter(
        Q(valid_until__isnull=True) | Q(valid_until__gte=day),
        staff=staff,
        privilege__code=code,
        privilege__is_active=True,
        status=StaffPrivilege.Status.ACTIVE,
        valid_from__lte=day,
    )
    if department is not None:
        grants = grants.filter(Q(department__isnull=True) | Q(department=department))
    return grants.exists()
