from itertools import pairwise

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
DEPARTMENT_UPDATABLE_FIELDS = ("name", "department_type", "status", "head")


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


# --- Department services and opening hours (HIMS-FAC-007, spec 4.2) ---------------------------

MAX_SESSIONS_PER_DAY = 4


@transaction.atomic
def set_department_hours(
    *, actor, department_id, version: int, open_24_hours: bool, sessions: list, request=None
):
    """Replace the whole weekly timetable at once (times are in the facility's time zone).

    ``sessions`` is a list of {weekday, opens_at, closes_at}. A day without sessions is closed.
    """
    from .models import DepartmentHours

    department = lock_for_update(Department, pk=department_id, expected_version=version)
    errors = []
    by_day: dict[int, list] = {}
    for session in sessions:
        if session["closes_at"] <= session["opens_at"]:
            errors.append(f"{_day(session['weekday'])}: closing time must be after opening time.")
        by_day.setdefault(session["weekday"], []).append(session)
    for weekday, day_sessions in sorted(by_day.items()):
        if len(day_sessions) > MAX_SESSIONS_PER_DAY:
            errors.append(f"{_day(weekday)}: at most {MAX_SESSIONS_PER_DAY} sessions per day.")
        ordered = sorted(day_sessions, key=lambda s: s["opens_at"])
        for earlier, later in pairwise(ordered):
            if later["opens_at"] < earlier["closes_at"]:
                errors.append(f"{_day(weekday)}: sessions overlap.")
                break
    if errors:
        from django.core.exceptions import ValidationError

        raise ValidationError({"sessions": errors})

    before = {"open_24_hours": department.open_24_hours, "hours": _hours_text(department)}
    DepartmentHours.objects.filter(department=department).delete()  # timetable rows only
    DepartmentHours.objects.bulk_create(
        [
            DepartmentHours(
                department=department,
                weekday=s["weekday"],
                opens_at=s["opens_at"],
                closes_at=s["closes_at"],
            )
            for s in sessions
        ]
    )
    department.open_24_hours = open_24_hours
    bump_version(department)
    department.save(update_fields=["open_24_hours", "version", "updated_at"])
    after = {"open_24_hours": open_24_hours, "hours": _hours_text(department)}
    record_audit_event(
        action=AuditAction.DEPARTMENT_HOURS_CHANGED,
        resource_type="department",
        resource_id=department.pk,
        facility_id=department.facility_id,
        actor=actor,
        request=request,
        changes={"before": before, "after": after},
    )
    return department


def _day(weekday: int) -> str:
    from .models import DepartmentHours

    return DepartmentHours.Weekday(weekday).label


def _hours_text(department) -> list[str]:
    return [str(h) for h in department.hours.all()]


@transaction.atomic
def create_department_service(*, actor, department, name: str, description: str = "", request=None):
    from .models import DepartmentService

    if department.status != Department.Status.ACTIVE:
        raise ConflictError("Services can only be added to an active department.")
    service = DepartmentService(
        organization_id=department.organization_id,
        department=department,
        name=name.strip(),
        description=description.strip(),
    )
    service.full_clean()
    service.save()
    record_audit_event(
        action=AuditAction.DEPARTMENT_SERVICE_CREATED,
        resource_type="department_service",
        resource_id=service.pk,
        facility_id=department.facility_id,
        actor=actor,
        request=request,
        changes={"after": snapshot(service)},
    )
    return service


@transaction.atomic
def update_department_service(*, actor, service_id, version: int, request=None, **changes):
    from .models import DepartmentService

    allowed = ("name", "description", "is_active")
    service = lock_for_update(DepartmentService, pk=service_id, expected_version=version)
    before = snapshot(service, allowed)
    _apply(service, changes, allowed)
    service.full_clean()
    bump_version(service)
    service.save()
    record_audit_event(
        action=AuditAction.DEPARTMENT_SERVICE_UPDATED,
        resource_type="department_service",
        resource_id=service.pk,
        facility_id=service.department.facility_id,
        actor=actor,
        request=request,
        changes=model_changes(before, snapshot(service, allowed)),
    )
    return service
