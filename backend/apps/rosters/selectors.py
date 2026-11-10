"""Read side of rotas and leave: the week grid, who is on call now, and a person's own schedule
(HIMS-STAFF-012)."""

from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.access_control.selectors import get_permission_scope
from apps.features.catalog import F
from apps.features.services import disabled_facility_ids
from apps.organizations.dates import hospital_today
from apps.staff.models import StaffDepartmentAssignment, StaffMember

from . import balances, staffing
from .models import LeaveRequest, Shift, ShiftType

WORKING = (StaffMember.EmploymentStatus.ACTIVE, StaffMember.EmploymentStatus.ON_LEAVE)
SHOWN_LEAVE = (LeaveRequest.Status.REQUESTED, LeaveRequest.Status.APPROVED)


def shift_queryset():
    return Shift.objects.select_related("staff", "department", "facility", "shift_type")


def scope_filter(
    user, codename: str, *, facility_field="facility_id", department_field="department_id"
):
    """Rows whose facility or department the person's grant covers (None = everything)."""
    scope = get_permission_scope(user, codename)
    if scope.org_wide:
        return None
    q = Q(**{f"{facility_field}__in": scope.facility_ids})
    for facility_id, department_id in scope.department_ids:
        q |= Q(**{facility_field: facility_id, department_field: department_id})
    return q


def rota_week(department, start: date, *, leave_details: bool) -> dict:
    """Everyone posted in the department during the week (or planned there), with their shifts
    and time away. The kind of leave is shown only to people who decide leave."""
    end = start + timedelta(days=6)
    postings = (
        StaffDepartmentAssignment.objects.filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=start),
            department=department,
            valid_from__lte=end,
            staff__employment_status__in=WORKING,
        )
        .select_related("staff", "designation")
        .order_by("-designation__seniority", "staff__family_name", "staff__given_name")
    )
    shifts = list(
        shift_queryset()
        .filter(department=department, on_date__gte=start, on_date__lte=end)
        .order_by("starts_at")
    )
    people: dict = {}
    for posting in postings:
        people.setdefault(
            posting.staff_id,
            {"staff": posting.staff, "designation": posting.designation.name},
        )
    for shift in shifts:
        people.setdefault(shift.staff_id, {"staff": shift.staff, "designation": None})
    leave = LeaveRequest.objects.filter(
        staff_id__in=people,
        status__in=SHOWN_LEAVE,
        start_date__lte=end,
        end_date__gte=start,
    ).order_by("start_date")
    rows = []
    for staff_id, info in people.items():
        staff = info["staff"]
        rows.append(
            {
                "staff_id": staff_id,
                "name": f"{staff.given_name} {staff.family_name}",
                "designation": info["designation"],
                "shifts": [s for s in shifts if s.staff_id == staff_id],
                "away": [
                    {
                        "leave_id": item.pk,
                        "start_date": item.start_date,
                        "end_date": item.end_date,
                        "status": item.status,
                        "leave_type": item.leave_type if leave_details else None,
                        "leave_type_label": item.get_leave_type_display()
                        if leave_details
                        else None,
                    }
                    for item in leave
                    if item.staff_id == staff_id
                ],
            }
        )
    today = hospital_today(department.facility)
    return {
        # Only from today on: a past gap cannot be filled any more.
        "staffing_gaps": staffing.gaps(department, max(start, today), end),
        "department_id": department.pk,
        "department_name": department.name,
        "facility_id": department.facility_id,
        "facility_name": department.facility.name,
        "start": start,
        "days": [start + timedelta(days=n) for n in range(7)],
        "people": rows,
    }


def happening_now(user, codename: str, *, facility_id=None, request=None) -> dict:
    """Shifts and on-call running now in the departments the person may see."""
    now = timezone.now()
    rows = shift_queryset().filter(
        status=Shift.Status.SCHEDULED, starts_at__lte=now, ends_at__gt=now
    )
    visible = scope_filter(user, codename)
    if visible is not None:
        rows = rows.filter(visible)
    if facility_id:
        rows = rows.filter(facility_id=facility_id)
    off = disabled_facility_ids(F.ROTAS, request=request)
    if off:
        rows = rows.exclude(facility_id__in=off)
    rows = list(rows.order_by("department__name", "ends_at"))
    return {
        "at": now,
        "on_call": [s for s in rows if s.shift_type.kind == ShiftType.Kind.ON_CALL],
        "working": [s for s in rows if s.shift_type.kind == ShiftType.Kind.SHIFT],
    }


def my_schedule(user) -> dict:
    """The signed-in person's own postings, shifts (last week to six weeks ahead) and leave."""
    staff = StaffMember.objects.filter(user=user).first()
    if staff is None:
        return {
            "has_staff_record": False,
            "postings": [],
            "shifts": [],
            "leave": [],
            "leave_balances": [],
        }
    today = hospital_today()
    postings = (
        StaffDepartmentAssignment.objects.filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=today),
            staff=staff,
            valid_from__lte=today + timedelta(days=60),
        )
        .select_related("department", "department__facility")
        .order_by("-is_primary", "department__name")
    )
    return {
        "has_staff_record": True,
        "name": f"{staff.given_name} {staff.family_name}",
        "leave_balances": balances.balances_for([staff])[staff.pk],
        "postings": [
            {
                "department_id": p.department_id,
                "department_name": p.department.name,
                "facility_name": p.department.facility.name,
                "is_primary": p.is_primary,
            }
            for p in postings
        ],
        "shifts": list(
            shift_queryset()
            .filter(
                staff=staff,
                on_date__gte=today - timedelta(days=7),
                on_date__lte=today + timedelta(days=42),
            )
            .order_by("starts_at")
        ),
        "leave": list(
            LeaveRequest.objects.filter(staff=staff, end_date__gte=today - timedelta(days=365))
            .select_related("staff", "department", "decided_by", "requested_by")
            .order_by("-start_date")[:100]
        ),
    }
