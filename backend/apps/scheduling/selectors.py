"""Read side of doctor OPD schedules: one department's week, one doctor's day with its slots, and
your own sessions (HIMS-OPD-001)."""

from datetime import date, timedelta

from django.db.models import Q

from apps.rosters.selectors import WORKING
from apps.staff.models import StaffDepartmentAssignment, StaffMember

from . import availability
from .models import DoctorSchedule, ScheduleException
from .services import OPD_STAFF_TYPES


def schedule_queryset():
    return DoctorSchedule.objects.select_related("staff", "department", "facility")


def exception_queryset():
    return ScheduleException.objects.select_related("staff", "department", "facility")


def _name(staff: StaffMember) -> str:
    return f"{staff.given_name} {staff.family_name}"


def _doctors(department, first: date, last: date) -> list[dict]:
    """Doctors posted in the department during these days, and anyone holding sessions there
    (a posting that ended shows why their sessions are off)."""
    found: dict = {}
    postings = (
        StaffDepartmentAssignment.objects.filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=first),
            department=department,
            valid_from__lte=last,
            staff__staff_type__in=OPD_STAFF_TYPES,
            staff__employment_status__in=WORKING,
        )
        .select_related("staff", "designation")
        .order_by("-designation__seniority", "staff__family_name", "staff__given_name")
    )
    for posting in postings:
        found.setdefault(
            posting.staff_id, {"staff": posting.staff, "designation": posting.designation.name}
        )
    holding = (
        DoctorSchedule.objects.filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=first),
            department=department,
            is_active=True,
            valid_from__lte=last,
        )
        .exclude(staff_id__in=found)
        .select_related("staff")
    )
    for schedule in holding:
        found.setdefault(schedule.staff_id, {"staff": schedule.staff, "designation": None})
    return list(found.values())


def department_week(department, start: date, *, details: bool) -> dict:
    """The department's doctors over seven days: each day's sessions with what takes them off,
    the weekly sessions behind them, and the exceptions that apply (to change or cancel)."""
    end = start + timedelta(days=6)
    doctors = _doctors(department, start, end)
    staff_ids = [d["staff"].pk for d in doctors]
    plan = availability.plan_for(
        staff_ids=staff_ids, first=start, last=end, department=department, details=details
    )
    schedules = list(
        schedule_queryset()
        .filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=start),
            department=department,
            staff_id__in=staff_ids,
            is_active=True,
        )
        .order_by("weekday", "start_time")
    )
    exceptions = (
        exception_queryset()
        .filter(
            Q(kind=ScheduleException.Kind.LEAVE, staff_id__in=staff_ids)
            | Q(kind=ScheduleException.Kind.EXTRA_SESSION, department=department)
            | Q(
                Q(department__isnull=True) | Q(department=department),
                kind=ScheduleException.Kind.HOLIDAY,
                facility_id=department.facility_id,
            ),
            status=ScheduleException.Status.ACTIVE,
            start_date__lte=end,
            end_date__gte=start,
        )
        .order_by("start_date", "start_time")
    )
    days = [start + timedelta(days=n) for n in range(7)]
    rows = []
    for doctor in doctors:
        staff = doctor["staff"]
        rows.append(
            {
                "staff_id": staff.pk,
                "name": _name(staff),
                "designation": doctor["designation"],
                "weekly": [s for s in schedules if s.staff_id == staff.pk],
                "days": [
                    {
                        "day": day,
                        "leave_asked": (staff.pk, day) in plan.leave_asked,
                        "sessions": [availability.session_out(s) for s in plan.on(staff.pk, day)],
                    }
                    for day in days
                ],
            }
        )
    return {
        "department_id": department.pk,
        "department_name": department.name,
        "facility_id": department.facility_id,
        "facility_name": department.facility.name,
        "start": start,
        "days": days,
        "doctors": rows,
        "exceptions": list(exceptions),
    }


def doctor_day(staff: StaffMember, day: date, *, department=None, details: bool) -> dict:
    """One doctor's sessions on one day, in every department or one, with each open slot."""
    plan = availability.plan_for(
        staff_ids=[staff.pk], first=day, last=day, department=department, details=details
    )
    return {
        "staff_id": staff.pk,
        "name": _name(staff),
        "day": day,
        "leave_asked": (staff.pk, day) in plan.leave_asked,
        "sessions": [availability.session_out(s, with_slots=True) for s in plan.on(staff.pk, day)],
    }


def my_week(staff: StaffMember, start: date) -> dict:
    """Your own OPD sessions over seven days, in every department (your own reasons shown)."""
    end = start + timedelta(days=6)
    plan = availability.plan_for(staff_ids=[staff.pk], first=start, last=end, details=True)
    days = [start + timedelta(days=n) for n in range(7)]
    return {
        "start": start,
        "days": [
            {
                "day": day,
                "leave_asked": (staff.pk, day) in plan.leave_asked,
                "sessions": [availability.session_out(s) for s in plan.on(staff.pk, day)],
            }
            for day in days
        ],
    }
