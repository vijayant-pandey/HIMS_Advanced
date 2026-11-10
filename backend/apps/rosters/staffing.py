"""Minimum staffing per shift and alerts for gaps (HIMS-STAFF-015; spec 4.3). The hospital sets the
numbers (CLIN, 2026-11-08: fine for now); HIMS has no staffing ratios of its own.

A gap warns and never blocks: a planner may know better, and a rota must always be plannable.
See docs/workflows/minimum-staffing.md.
"""

from collections import Counter
from datetime import date, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.access_control.catalog import P
from apps.audit.services import AuditAction, model_changes, record_audit_event, snapshot
from apps.facilities.models import Department
from apps.features.catalog import F
from apps.features.services import disabled_facility_ids
from apps.notifications.services import send_message
from apps.organizations.dates import hospital_today
from apps.staff.models import StaffMember
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError

from .models import Shift, StaffingGapAlert, StaffingRequirement

ALERT_DAYS = 7
REQUIREMENT_FIELDS = ["minimum", "is_active"]
AppliesOn = StaffingRequirement.AppliesOn


def _applies(requirement: StaffingRequirement, day: date) -> bool:
    weekend = day.weekday() >= 5
    return (
        requirement.applies_on == AppliesOn.EVERY_DAY
        or (requirement.applies_on == AppliesOn.WEEKENDS and weekend)
        or (requirement.applies_on == AppliesOn.WEEKDAYS and not weekend)
    )


def _overlapping(department, shift_type, staff_type, applies_on, *, exclude=None):
    """Active rows that would count the same people on the same days."""
    rows = StaffingRequirement.objects.filter(
        department=department, shift_type=shift_type, staff_type=staff_type, is_active=True
    )
    if exclude is not None:
        rows = rows.exclude(pk=exclude)
    if applies_on != AppliesOn.EVERY_DAY:
        rows = rows.filter(applies_on__in=[applies_on, AppliesOn.EVERY_DAY])
    return rows


@transaction.atomic
def create_requirement(
    *,
    actor,
    department,
    shift_type,
    minimum: int,
    staff_type: str = "",
    applies_on: str = AppliesOn.EVERY_DAY,
    request=None,
) -> StaffingRequirement:
    if _overlapping(department, shift_type, staff_type, applies_on).exists():
        raise ConflictError(
            "This shift already has a minimum for these people on some of these days. Change it, "
            "or switch it off first.",
            code="DUPLICATE_REQUIREMENT",
        )
    row = StaffingRequirement(
        organization_id=department.organization_id,
        facility_id=department.facility_id,
        department=department,
        shift_type=shift_type,
        staff_type=staff_type,
        applies_on=applies_on,
        minimum=minimum,
    )
    row.full_clean()
    try:
        with transaction.atomic():
            row.save()
    except IntegrityError:
        raise ConflictError(
            "This shift already has this minimum, switched off. Switch it back on instead.",
            code="DUPLICATE_REQUIREMENT",
        ) from None
    record_audit_event(
        action=AuditAction.STAFFING_REQUIREMENT_CREATED,
        resource_type="staffing_requirement",
        resource_id=row.pk,
        facility_id=row.facility_id,
        actor=actor,
        request=request,
        changes={
            "after": snapshot(
                row, ["department_id", "shift_type_id", "staff_type", "applies_on", "minimum"]
            )
        },
    )
    return row


@transaction.atomic
def update_requirement(*, actor, requirement_id, version: int, request=None, **changes):
    row = lock_for_update(StaffingRequirement, pk=requirement_id, expected_version=version)
    before = snapshot(row, REQUIREMENT_FIELDS)
    for field, value in changes.items():
        if field not in REQUIREMENT_FIELDS:
            raise ValueError(f"{field} is not updatable")
        setattr(row, field, value)
    if (
        row.is_active
        and _overlapping(
            row.department_id, row.shift_type_id, row.staff_type, row.applies_on, exclude=row.pk
        ).exists()
    ):
        raise ConflictError(
            "Another minimum already covers these people on some of these days.",
            code="DUPLICATE_REQUIREMENT",
        )
    row.full_clean()
    bump_version(row)
    row.save()
    record_audit_event(
        action=AuditAction.STAFFING_REQUIREMENT_UPDATED,
        resource_type="staffing_requirement",
        resource_id=row.pk,
        facility_id=row.facility_id,
        actor=actor,
        request=request,
        changes=model_changes(before, snapshot(row, REQUIREMENT_FIELDS)),
    )
    return row


def gaps(department, first: date, last: date) -> list[dict]:
    """Every shift in these days with fewer people planned than the hospital's minimum."""
    requirements = list(
        StaffingRequirement.objects.filter(
            department=department, is_active=True, shift_type__is_active=True
        ).select_related("shift_type")
    )
    if not requirements or last < first:
        return []
    planned = Counter()
    for shift_type_id, on_date, staff_type in Shift.objects.filter(
        department=department,
        status=Shift.Status.SCHEDULED,
        on_date__gte=first,
        on_date__lte=last,
    ).values_list("shift_type_id", "on_date", "staff__staff_type"):
        planned[(shift_type_id, on_date, staff_type)] += 1
        planned[(shift_type_id, on_date, "")] += 1
    labels = dict(StaffMember.StaffType.choices)
    found = []
    for offset in range((last - first).days + 1):
        day = first + timedelta(days=offset)
        for requirement in requirements:
            if not _applies(requirement, day):
                continue
            count = planned[(requirement.shift_type_id, day, requirement.staff_type)]
            if count < requirement.minimum:
                found.append(
                    {
                        "on_date": day,
                        "shift_type_id": requirement.shift_type_id,
                        "shift_type_name": requirement.shift_type.name,
                        "staff_type": requirement.staff_type,
                        "staff_type_label": labels.get(requirement.staff_type, "Anyone"),
                        "minimum": requirement.minimum,
                        "planned": count,
                        "short_by": requirement.minimum - count,
                    }
                )
    return found


def _describe(gap: dict) -> str:
    who = "" if not gap["staff_type"] else f" {gap['staff_type_label'].lower()}"
    return (
        f"- {gap['on_date']:%a %d %b}, {gap['shift_type_name']}: {gap['planned']} of "
        f"{gap['minimum']}{who} planned"
    )


def send_staffing_gap_alerts(today: date | None = None) -> int:
    """Daily: tell a department's planners about gaps in the next 7 days. Each gap is told once,
    so an unfilled shift does not repeat every morning. Safe to run any number of times. Returns
    how many gaps were told."""
    from .services import planner_emails

    off = disabled_facility_ids(F.ROTAS)
    told = 0
    departments = (
        Department.objects.filter(
            status=Department.Status.ACTIVE,
            pk__in=StaffingRequirement.objects.filter(is_active=True).values("department_id"),
        )
        .exclude(facility_id__in=off)
        .select_related("facility")
    )
    for department in departments:
        first = today or hospital_today(department.facility)
        found = gaps(department, first, first + timedelta(days=ALERT_DAYS - 1))
        recipients = planner_emails(department, P.ROTA_MANAGE)
        if not found or not recipients:
            continue
        fresh = [gap for gap in found if _first_time(department, gap)]
        if not fresh:
            continue
        link = f"{settings.HIMS_APP_BASE_URL.rstrip('/')}/rota"
        send_message(
            "rosters.staffing_gaps",
            to=recipients,
            values={
                "department": department.name,
                "count": len(fresh),
                "gaps": "\n".join(_describe(gap) for gap in fresh),
                "link": link,
            },
            related=("department", department.pk),
        )
        record_audit_event(
            action=AuditAction.STAFFING_GAP_ALERT_SENT,
            resource_type="department",
            resource_id=department.pk,
            facility_id=department.facility_id,
            organization_id=department.organization_id,
            metadata={"gaps": len(fresh), "recipients": len(recipients)},
        )
        told += len(fresh)
    return told


def _first_time(department, gap: dict) -> bool:
    _row, created = StaffingGapAlert.objects.get_or_create(
        department=department,
        shift_type_id=gap["shift_type_id"],
        staff_type=gap["staff_type"],
        on_date=gap["on_date"],
        defaults={"sent_at": timezone.now()},
    )
    return created
