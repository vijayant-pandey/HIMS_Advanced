from django.db import transaction

from apps.audit.services import AuditAction, model_changes, record_audit_event, snapshot
from apps.organizations.selectors import get_deployment_organization
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError

from .models import Department, Facility

FACILITY_UPDATABLE_FIELDS = (
    "name",
    "facility_type",
    "state_region",
    "city",
    "address_line1",
    "address_line2",
    "postal_code",
    "timezone",
    "phone",
    "status",
)
DEPARTMENT_UPDATABLE_FIELDS = ("name", "department_type", "status")


def _apply(instance, changes: dict, allowed: tuple[str, ...]) -> None:
    for field, value in changes.items():
        if field not in allowed:
            raise ValueError(f"{field} is not updatable")
        setattr(instance, field, value)


@transaction.atomic
def create_facility(*, actor, request=None, **data) -> Facility:
    organization = get_deployment_organization()
    if Facility.objects.filter(organization=organization, code=data["code"]).exists():
        raise ConflictError("A facility with this code already exists.", code="DUPLICATE_CODE")
    facility = Facility(organization=organization, **data)
    facility.full_clean()
    facility.save()
    record_audit_event(
        action=AuditAction.FACILITY_CREATED,
        resource_type="facility",
        resource_id=facility.pk,
        facility_id=facility.pk,
        actor=actor,
        request=request,
        changes={"after": snapshot(facility)},
    )
    return facility


@transaction.atomic
def update_facility(*, actor, facility_id, version: int, request=None, **changes) -> Facility:
    facility = lock_for_update(Facility, pk=facility_id, expected_version=version)
    before = snapshot(facility, FACILITY_UPDATABLE_FIELDS)
    _apply(facility, changes, FACILITY_UPDATABLE_FIELDS)
    facility.full_clean()
    bump_version(facility)
    facility.save()
    record_audit_event(
        action=AuditAction.FACILITY_UPDATED,
        resource_type="facility",
        resource_id=facility.pk,
        facility_id=facility.pk,
        actor=actor,
        request=request,
        changes=model_changes(before, snapshot(facility, FACILITY_UPDATABLE_FIELDS)),
    )
    return facility


@transaction.atomic
def create_department(*, actor, facility: Facility, request=None, **data) -> Department:
    if facility.status != Facility.Status.ACTIVE:
        raise ConflictError("Departments can only be added to an active facility.")
    if Department.objects.filter(facility=facility, code=data["code"]).exists():
        raise ConflictError("A department with this code already exists.", code="DUPLICATE_CODE")
    department = Department(organization_id=facility.organization_id, facility=facility, **data)
    department.full_clean()
    department.save()
    record_audit_event(
        action=AuditAction.DEPARTMENT_CREATED,
        resource_type="department",
        resource_id=department.pk,
        facility_id=facility.pk,
        actor=actor,
        request=request,
        changes={"after": snapshot(department)},
    )
    return department


@transaction.atomic
def update_department(*, actor, department_id, version: int, request=None, **changes):
    department = lock_for_update(Department, pk=department_id, expected_version=version)
    before = snapshot(department, DEPARTMENT_UPDATABLE_FIELDS)
    _apply(department, changes, DEPARTMENT_UPDATABLE_FIELDS)
    department.full_clean()
    bump_version(department)
    department.save()
    record_audit_event(
        action=AuditAction.DEPARTMENT_UPDATED,
        resource_type="department",
        resource_id=department.pk,
        facility_id=department.facility_id,
        actor=actor,
        request=request,
        changes=model_changes(before, snapshot(department, DEPARTMENT_UPDATABLE_FIELDS)),
    )
    return department
