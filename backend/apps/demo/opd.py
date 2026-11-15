"""Doctors' OPD sessions for the demo hospitals (HIMS-OPD-001). All people are invented.

Per branch, in each outpatient department: the consultant holds Monday, Wednesday and Friday
mornings (09:00-13:00, 10-minute slots, 2 extra bookings), the junior doctor Tuesday and
Thursday afternoons (14:00-17:00, 15-minute slots). Then one of each exception: the cardiologist
away for part of next Wednesday, the general physician away for three days at a conference, the
paediatrician's extra Saturday session, and a holiday (the first branch closes for a day, the
others close one department). Approved leave on the Leave page (made by the rota part of the seed)
takes some junior doctors' sessions off by itself.

Used by the seed and, for a hospital filled before HIMS-OPD-001 (the hosted Development hospital),
by ``add_demo_doctor_schedules``. Everything goes through the services, so every rule is checked
and every change is in the audit log.
"""

from datetime import date, time, timedelta

from django.db.models import Q

from apps.facilities.models import Department, Facility
from apps.organizations.dates import hospital_today
from apps.scheduling.models import ScheduleException
from apps.scheduling.services import add_exception, add_sessions
from apps.staff.models import StaffDepartmentAssignment, StaffMember

OPD_DEPARTMENTS = ("GMED", "CARD", "ORTH", "PAED", "OBGY", "GSUR")
# (weekdays, start, end, slot minutes, extra bookings) for the first and second doctor.
PATTERNS = (
    ((0, 2, 4), time(9), time(13), 10, 2),
    ((1, 3), time(14), time(17), 15, 0),
)


def _doctors(department: Department) -> list[StaffMember]:
    """The department's working doctors, the most senior first."""
    today = hospital_today(department.facility)
    postings = (
        StaffDepartmentAssignment.objects.filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=today),
            department=department,
            valid_from__lte=today,
            staff__staff_type=StaffMember.StaffType.DOCTOR,
            staff__employment_status=StaffMember.EmploymentStatus.ACTIVE,
        )
        .select_related("staff")
        .order_by("-designation__seniority", "staff__created_at")
    )
    found = []
    for posting in postings:
        if posting.staff not in found:
            found.append(posting.staff)
    return found


def _next(weekday: int, after: date) -> date:
    day = after + timedelta(days=1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day


def add_opd_examples(*, actor) -> list[str]:
    """Add the sessions and exceptions to every branch; returns lines saying what to look at."""
    notes = []
    for n, facility in enumerate(Facility.objects.order_by("created_at")):
        today = hospital_today(facility)
        departments = {
            d.code: d
            for d in Department.objects.filter(
                facility=facility, code__in=OPD_DEPARTMENTS, status=Department.Status.ACTIVE
            ).select_related("facility")
        }
        heads = {}
        for code in OPD_DEPARTMENTS:
            department = departments.get(code)
            if department is None:
                continue
            doctors = _doctors(department)
            for k, (doctor, pattern) in enumerate(zip(doctors, PATTERNS, strict=False)):
                weekdays, start, end, slot, extra = pattern
                add_sessions(
                    actor=actor,
                    staff=doctor,
                    department=department,
                    weekdays=weekdays,
                    start_time=start,
                    end_time=end,
                    slot_minutes=slot,
                    extra_bookings_allowed=extra,
                    valid_from=today,
                    note=f"OPD room {k + 1}",
                )
            if doctors:
                heads[code] = doctors[0]

        wednesday = _next(2, today)
        for code, start_date, reason, extra in (
            (
                "CARD",
                wednesday,
                "Hospital committee meeting",
                {"start_time": time(11), "end_time": time(13)},
            ),
            (
                "GMED",
                today + timedelta(days=8),
                "Medical conference",
                {"end_date": today + timedelta(days=10)},
            ),
        ):
            if code in heads:
                add_exception(
                    actor=actor,
                    kind=ScheduleException.Kind.LEAVE,
                    facility=facility,
                    staff=heads[code],
                    department=departments[code],
                    start_date=start_date,
                    reason=reason,
                    **extra,
                )
        if "PAED" in heads:
            add_exception(
                actor=actor,
                kind=ScheduleException.Kind.EXTRA_SESSION,
                facility=facility,
                staff=heads["PAED"],
                department=departments["PAED"],
                start_date=_next(5, today),
                start_time=time(14),
                end_time=time(16),
                slot_minutes=15,
                reason="Vaccination drive",
            )
        if n == 0:
            add_exception(
                actor=actor,
                kind=ScheduleException.Kind.HOLIDAY,
                facility=facility,
                start_date=today + timedelta(days=16),
                reason="Hospital foundation day",
            )
            notes.append(
                f"{facility.name}: OPD closed on {today + timedelta(days=16):%d %b} "
                "(Hospital foundation day)"
            )
        elif "ORTH" in departments:
            add_exception(
                actor=actor,
                kind=ScheduleException.Kind.HOLIDAY,
                facility=facility,
                department=departments["ORTH"],
                start_date=today + timedelta(days=12),
                reason="Department training day",
            )
        if "CARD" in heads:
            notes.append(
                f"{facility.name}: Cardiology, {wednesday:%a %d %b}: the consultant is away "
                "11:00-13:00 (the morning's first slots stay open)"
            )
    return notes
