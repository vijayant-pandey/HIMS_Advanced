from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditAction, model_changes, record_audit_event, snapshot
from apps.facilities.models import Department
from apps.identity.services import create_user
from apps.organizations.selectors import get_deployment_organization
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError
from common.outbox.services import publish_event

from .models import (
    StaffCredential,
    StaffDepartmentAssignment,
    StaffMember,
    StaffQualification,
    VerificationStatus,
)

STAFF_UPDATABLE_FIELDS = ("given_name", "family_name", "staff_type", "employment_status", "left_on")


@transaction.atomic
def create_staff_member(*, actor, email: str | None = None, request=None, **data) -> StaffMember:
    organization = get_deployment_organization()
    if StaffMember.objects.filter(
        organization=organization, employee_number=data["employee_number"]
    ).exists():
        raise ConflictError(
            "A staff member with this employee number already exists.", code="DUPLICATE_CODE"
        )
    user = None
    if email:
        user = create_user(
            email=email,
            display_name=f"{data['given_name']} {data['family_name']}",
            actor=actor,
            request=request,
        )
    staff = StaffMember(organization=organization, user=user, **data)
    staff.full_clean()
    staff.save()
    record_audit_event(
        action=AuditAction.STAFF_CREATED,
        resource_type="staff_member",
        resource_id=staff.pk,
        actor=actor,
        request=request,
        changes={"after": snapshot(staff)},
    )
    emit_staff_created(staff)
    return staff


def emit_staff_created(staff: StaffMember) -> None:
    """Consumers: invitation email (HIMS-IAM-003), directory sync. Payload carries IDs only."""
    publish_event(
        event_type="staff.member.created",
        aggregate_type="staff_member",
        aggregate_id=staff.pk,
        payload={
            "staff_member_id": str(staff.pk),
            "user_id": str(staff.user_id) if staff.user_id else None,
        },
    )


def apply_employment_status_change(staff: StaffMember) -> None:
    """Side effects of an employment-status change, shared by the API and the admin console.

    Suspension/termination ends access immediately: inactive users fail authentication and lose
    every grant (spec 13.2, 13.5), and deactivating the account deletes all of the person's
    sessions on every device (apps.identity.sessions, HIMS-IAM-006).
    """
    if staff.user_id:
        user = staff.user
        user.is_active = staff.employment_status in (
            StaffMember.EmploymentStatus.ACTIVE,
            StaffMember.EmploymentStatus.ON_LEAVE,
        )
        if not user.is_active:
            from apps.identity.accounts import ensure_not_last_administrator

            ensure_not_last_administrator(user)  # the hospital must never be locked out
        user.save(update_fields=["is_active"])
    publish_event(
        event_type="staff.member.employment_status_changed",
        aggregate_type="staff_member",
        aggregate_id=staff.pk,
        payload={"staff_member_id": str(staff.pk), "employment_status": staff.employment_status},
    )


@transaction.atomic
def update_staff_member(*, actor, staff_id, version: int, request=None, **changes) -> StaffMember:
    staff = lock_for_update(StaffMember, pk=staff_id, expected_version=version)
    before = snapshot(staff, STAFF_UPDATABLE_FIELDS)
    for field, value in changes.items():
        if field not in STAFF_UPDATABLE_FIELDS:
            raise ValueError(f"{field} is not updatable")
        setattr(staff, field, value)
    staff.full_clean()
    bump_version(staff)
    staff.save()

    record_audit_event(
        action=AuditAction.STAFF_UPDATED,
        resource_type="staff_member",
        resource_id=staff.pk,
        actor=actor,
        request=request,
        changes=model_changes(before, snapshot(staff, STAFF_UPDATABLE_FIELDS)),
    )
    if before["employment_status"] != staff.employment_status:
        apply_employment_status_change(staff)
    return staff


@transaction.atomic
def add_department_assignment(
    *, actor, staff: StaffMember, department: Department, request=None, **data
) -> StaffDepartmentAssignment:
    if department.status != Department.Status.ACTIVE:
        raise ConflictError("Staff can only be assigned to an active department.")
    if data.get("is_primary"):
        StaffDepartmentAssignment.objects.filter(staff=staff, is_primary=True).update(
            is_primary=False
        )
    assignment = StaffDepartmentAssignment(
        organization_id=staff.organization_id, staff=staff, department=department, **data
    )
    assignment.full_clean()
    assignment.save()
    record_audit_event(
        action=AuditAction.STAFF_DEPARTMENT_ASSIGNED,
        resource_type="staff_department_assignment",
        resource_id=assignment.pk,
        facility_id=department.facility_id,
        actor=actor,
        request=request,
        changes={"after": snapshot(assignment)},
    )
    return assignment


@transaction.atomic
def add_qualification(*, actor, staff: StaffMember, request=None, **data) -> StaffQualification:
    qualification = StaffQualification(organization_id=staff.organization_id, staff=staff, **data)
    qualification.full_clean()
    qualification.save()
    record_audit_event(
        action=AuditAction.STAFF_QUALIFICATION_ADDED,
        resource_type="staff_qualification",
        resource_id=qualification.pk,
        actor=actor,
        request=request,
        changes={"after": snapshot(qualification)},
    )
    return qualification


@transaction.atomic
def add_credential(*, actor, staff: StaffMember, request=None, **data) -> StaffCredential:
    if StaffCredential.objects.filter(
        organization_id=staff.organization_id,
        credential_type=data["credential_type"],
        issuing_authority=data["issuing_authority"],
        registration_number=data["registration_number"],
    ).exists():
        raise ConflictError("This credential is already registered.", code="DUPLICATE_CREDENTIAL")
    credential = StaffCredential(organization_id=staff.organization_id, staff=staff, **data)
    credential.full_clean()
    credential.save()
    record_audit_event(
        action=AuditAction.STAFF_CREDENTIAL_ADDED,
        resource_type="staff_credential",
        resource_id=credential.pk,
        actor=actor,
        request=request,
        changes={"after": snapshot(credential)},
    )
    publish_event(
        event_type="staff.credential.added",
        aggregate_type="staff_credential",
        aggregate_id=credential.pk,
        payload={"staff_member_id": str(staff.pk), "credential_id": str(credential.pk)},
    )
    return credential


@transaction.atomic
def verify_credential(
    *, actor, credential_id, verified: bool, request=None, reason: str = ""
) -> StaffCredential:
    credential = (
        StaffCredential.objects.select_for_update().select_related("staff").get(pk=credential_id)
    )
    if credential.staff.user_id and credential.staff.user_id == actor.pk:
        raise ConflictError("You cannot verify your own credential.", code="SELF_VERIFICATION")
    if credential.verification_status != VerificationStatus.UNVERIFIED:
        raise ConflictError(
            "Only unverified credentials can be verified or rejected.",
            code="INVALID_STATE_TRANSITION",
        )
    credential.verification_status = (
        VerificationStatus.VERIFIED if verified else VerificationStatus.REJECTED
    )
    credential.verified_by = actor
    credential.verified_at = timezone.now()
    credential.save(
        update_fields=["verification_status", "verified_by", "verified_at", "updated_at"]
    )
    record_audit_event(
        action=AuditAction.STAFF_CREDENTIAL_VERIFIED,
        resource_type="staff_credential",
        resource_id=credential.pk,
        actor=actor,
        request=request,
        reason=reason,
        metadata={"result": credential.verification_status},
    )
    return credential


@transaction.atomic
def end_department_assignment(
    *, actor, staff: StaffMember, assignment_id, valid_until=None, reason: str = "", request=None
) -> StaffDepartmentAssignment:
    """Close a posting (transfer, resignation, end of rotation). The row stays for history."""
    assignment = (
        StaffDepartmentAssignment.objects.select_for_update()
        .select_related("department")
        .get(pk=assignment_id, staff=staff)
    )
    if assignment.valid_until is not None and assignment.valid_until < timezone.localdate():
        raise ConflictError("This posting has already ended.", code="ALREADY_ENDED")
    ended_on = valid_until or timezone.localdate()
    if ended_on < assignment.valid_from:
        raise ConflictError(
            "The end date cannot be before the posting started.", code="INVALID_END_DATE"
        )
    before = snapshot(assignment, ["valid_until", "is_primary"])
    assignment.valid_until = ended_on
    assignment.is_primary = False
    assignment.full_clean()
    assignment.save(update_fields=["valid_until", "is_primary", "updated_at"])
    record_audit_event(
        action=AuditAction.STAFF_DEPARTMENT_ASSIGNMENT_ENDED,
        resource_type="staff_department_assignment",
        resource_id=assignment.pk,
        facility_id=assignment.department.facility_id,
        actor=actor,
        request=request,
        reason=reason,
        changes=model_changes(before, snapshot(assignment, ["valid_until", "is_primary"])),
    )
    return assignment


@transaction.atomic
def verify_qualification(
    *, actor, staff: StaffMember, qualification_id, verified: bool, request=None, reason: str = ""
) -> StaffQualification:
    """Mark a degree/diploma as checked against the original (or rejected)."""
    qualification = StaffQualification.objects.select_for_update().get(
        pk=qualification_id, staff=staff
    )
    if staff.user_id and staff.user_id == actor.pk:
        raise ConflictError("You cannot verify your own qualification.", code="SELF_VERIFICATION")
    if qualification.verification_status != VerificationStatus.UNVERIFIED:
        raise ConflictError(
            "Only unverified qualifications can be verified or rejected.",
            code="INVALID_STATE_TRANSITION",
        )
    qualification.verification_status = (
        VerificationStatus.VERIFIED if verified else VerificationStatus.REJECTED
    )
    qualification.verified_by = actor
    qualification.verified_at = timezone.now()
    qualification.save(
        update_fields=["verification_status", "verified_by", "verified_at", "updated_at"]
    )
    record_audit_event(
        action=AuditAction.STAFF_QUALIFICATION_VERIFIED,
        resource_type="staff_qualification",
        resource_id=qualification.pk,
        actor=actor,
        request=request,
        reason=reason,
        metadata={"result": qualification.verification_status},
    )
    return qualification
