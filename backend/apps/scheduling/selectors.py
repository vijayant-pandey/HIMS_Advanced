"""Read side of doctor OPD schedules: one department's week, one doctor's day with its slots, and
your own sessions (HIMS-OPD-001); a department's day with its appointments, and the appointments
that must be moved because their session or slot is off (HIMS-OPD-002)."""

from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.organizations.dates import hospital_today
from apps.rosters.selectors import WORKING
from apps.staff.models import StaffDepartmentAssignment, StaffMember

from . import availability
from .booking import MAX_AHEAD_DAYS
from .models import ACTIVE_STATUSES, Appointment, DoctorSchedule, ScheduleException
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


# --- Appointments (HIMS-OPD-002) ---------------------------------------------------------------


def appointment_queryset():
    return Appointment.objects.select_related(
        "patient", "staff", "department", "facility", "booked_by", "rescheduled_to"
    )


def department_day(department, day: date, *, details: bool) -> dict:
    """One department's doctors on one day: each session with its slots (free or booked), and
    every appointment of the day there, cancelled ones too."""
    doctors = _doctors(department, day, day)
    staff_ids = [d["staff"].pk for d in doctors]
    plan = availability.plan_for(
        staff_ids=staff_ids, first=day, last=day, department=department, details=details
    )
    appointments = (
        appointment_queryset()
        .filter(staff_id__in=staff_ids, local_date=day, department=department)
        .order_by("starts_at", "created_at")
    )
    return {
        "department_id": department.pk,
        "department_name": department.name,
        "facility_id": department.facility_id,
        "facility_name": department.facility.name,
        "day": day,
        "doctors": [
            {
                "staff_id": d["staff"].pk,
                "name": _name(d["staff"]),
                "designation": d["designation"],
                "leave_asked": (d["staff"].pk, day) in plan.leave_asked,
                "sessions": [
                    availability.session_out(s, with_slots=True)
                    for s in plan.on(d["staff"].pk, day)
                ],
            }
            for d in doctors
        ],
        "appointments": list(appointments),
    }


def _why_off(appointment: Appointment, sessions) -> str:
    """Why a booked appointment can no longer be seen at its time ("" when it can)."""
    for session in sessions:
        if not (
            (appointment.schedule_id and session.schedule_id == appointment.schedule_id)
            or (
                appointment.extra_session_id
                and session.exception_id == appointment.extra_session_id
            )
        ):
            continue
        blocks = [
            b
            for b in session.off
            if b.start < appointment.ends_at and appointment.starts_at < b.end
        ]
        return blocks[0].reason if blocks else ""
    return "The session no longer runs that day (ended or cancelled)"


TO_MOVE_LIMIT = 200  # a doctor away for weeks with a full book: the soonest 200 at a time


def to_rebook(department, *, details: bool) -> list[dict]:
    """Booked appointments still to come in the department whose doctor is now away, on leave, or
    whose session ended or was taken off: the patients to move or cancel (P0 part 01 section 10).
    Worked out each time, so leave approved on the Leave page counts at once. At most
    ``TO_MOVE_LIMIT``, soonest first (the volume check measured a whole department's book at
    nearly a second)."""
    today = hospital_today(department.facility)
    # Only the columns needed to decide; the full rows are read for the ones shown.
    rows = list(
        Appointment.objects.filter(
            local_date__gte=today,
            local_date__lte=today + timedelta(days=MAX_AHEAD_DAYS),
            status=Appointment.Status.BOOKED,
            department=department,
            starts_at__gte=timezone.now(),
        )
        .only("staff_id", "local_date", "schedule_id", "extra_session_id", "starts_at", "ends_at")
        .order_by("starts_at")
    )
    if not rows:
        return []
    plan = availability.plan_for(
        staff_ids={a.staff_id for a in rows},
        first=today,
        last=max(a.local_date for a in rows),
        department=department,
        details=details,
    )
    why_by_id = {}
    for appointment in rows:
        why = _why_off(appointment, plan.on(appointment.staff_id, appointment.local_date))
        if why:
            why_by_id[appointment.pk] = why
            if len(why_by_id) == TO_MOVE_LIMIT:
                break  # the soonest first; the rest show as these are moved
    shown = appointment_queryset().filter(pk__in=list(why_by_id)).order_by("starts_at")
    return [{"appointment": a, "why": why_by_id[a.pk]} for a in shown]


def booked_during(staff_id, first: date, last: date) -> int:
    """How many patients are booked with this person on these days, still to come (shown when
    leave is decided on the Leave page)."""
    return Appointment.objects.filter(
        staff_id=staff_id,
        local_date__gte=first,
        local_date__lte=last,
        status__in=ACTIVE_STATUSES,
        starts_at__gte=timezone.now(),
    ).count()


# --- The OPD queue (HIMS-OPD-003) --------------------------------------------------------------


def queue_day(department, day: date, *, details: bool) -> dict:
    """One department's OPD queue on one day: the doctors with a session or a patient that day,
    and every appointment of the day there (waiting by token, then those still to come by time).
    Reads the doctors' day through ``appointment_staff_day_idx``, as the Appointments page does."""
    doctors = _doctors(department, day, day)
    staff_ids = [d["staff"].pk for d in doctors]
    plan = availability.plan_for(
        staff_ids=staff_ids, first=day, last=day, department=department, details=details
    )
    appointments = list(
        appointment_queryset()
        .filter(staff_id__in=staff_ids, local_date=day, department=department)
        .order_by("token_number", "starts_at", "created_at")
    )
    with_patients = {a.staff_id for a in appointments}
    rows = []
    for d in doctors:
        staff_id = d["staff"].pk
        sessions = plan.on(staff_id, day)
        if not sessions and staff_id not in with_patients:
            continue  # no OPD here that day
        rows.append(
            {
                "staff_id": staff_id,
                "name": _name(d["staff"]),
                "designation": d["designation"],
                "leave_asked": (staff_id, day) in plan.leave_asked,
                "sessions": [availability.session_out(s) for s in sessions],
            }
        )
    return {
        "department_id": department.pk,
        "department_name": department.name,
        "facility_id": department.facility_id,
        "facility_name": department.facility.name,
        "day": day,
        "is_today": day == hospital_today(department.facility),
        "doctors": rows,
        "appointments": appointments,
    }
