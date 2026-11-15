"""Which OPD sessions doctors hold on given days, what takes them off, and their slots
(HIMS-OPD-001; ADR-038).

Nothing here is stored: it is worked out from the weekly sessions, the exceptions, approved leave
on the Leave page (HIMS-STAFF-012), postings, the department's status and the doctor's
employment status. A fixed number of queries is used, whatever the number of days or doctors.

A session is cut into slots from its start (10 minutes by default). Whatever takes part of it off
(an hour of leave, a holiday from noon) removes the slots it touches; the rest stay open. Slots
are what appointments (HIMS-OPD-002) book: each session carries its bookings, so a slot shows as
booked and the week shows how many patients are booked.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.facilities.models import Department
from apps.organizations.dates import hospital_timezone
from apps.rosters.models import LeaveRequest
from apps.staff.models import StaffDepartmentAssignment, StaffMember

from .models import ACTIVE_STATUSES, Appointment, DoctorSchedule, ScheduleException

# Why a session (or part of it) is off. "leave" is an OPD leave exception; "rota_leave" is leave
# approved on the Leave page; the others come from the person or the department.
OFF_KINDS = (
    ("leave", "Doctor away (OPD leave)"),
    ("rota_leave", "On leave (approved on the Leave page)"),
    ("holiday", "Holiday"),
    ("not_working", "Not working (employment status)"),
    ("not_posted", "Not posted in the department"),
    ("department_closed", "Department closed"),
)


@dataclass
class Off:
    start: datetime
    end: datetime
    kind: str
    reason: str
    exception_id: object = None


@dataclass
class Booking:
    """An appointment holding a place in a session (booked, checked in or with the doctor)."""

    appointment_id: object
    start: datetime
    end: datetime
    is_extra: bool


@dataclass
class Session:
    staff_id: object
    department: Department
    day: date
    start: datetime
    end: datetime
    slot_minutes: int
    extra_bookings_allowed: int
    source: str  # "weekly" or "extra"
    schedule_id: object = None
    exception_id: object = None
    note: str = ""
    off: list[Off] = field(default_factory=list)
    bookings: list[Booking] = field(default_factory=list)

    @property
    def zone(self):
        return hospital_timezone(self.department.facility)

    @property
    def hours(self) -> str:
        return _hours(self.start, self.end, self.zone)

    def take_off(self, start: datetime, end: datetime, kind: str, reason: str, exception_id=None):
        start, end = max(start, self.start), min(end, self.end)
        if start < end:
            self.off.append(Off(start, end, kind, reason, exception_id))

    def open_windows(self) -> list[tuple[datetime, datetime]]:
        windows = [(self.start, self.end)]
        for block in self.off:
            remaining = []
            for start, end in windows:
                if block.end <= start or block.start >= end:
                    remaining.append((start, end))
                    continue
                if block.start > start:
                    remaining.append((start, block.start))
                if block.end < end:
                    remaining.append((block.end, end))
            windows = remaining
        return windows

    def slots(self) -> list[tuple[datetime, datetime]]:
        """Open slots, counted from the session's start so a part taken off keeps the rest on
        their usual times."""
        windows = self.open_windows()
        step = timedelta(minutes=self.slot_minutes)
        found, start = [], self.start
        while start + step <= self.end:
            if any(w_start <= start and start + step <= w_end for w_start, w_end in windows):
                found.append((start, start + step))
            start += step
        return found

    def is_taken(self, start: datetime, end: datetime, ignore=None) -> bool:
        """A booking (not an extra one, nor ``ignore``, the one being moved) holds this time."""
        return any(
            not b.is_extra and b.appointment_id != ignore and b.start < end and start < b.end
            for b in self.bookings
        )

    @property
    def extra_booked(self) -> int:
        return sum(1 for b in self.bookings if b.is_extra)

    @property
    def status(self) -> str:
        if not self.off:
            return "open"
        return "off" if not self.slots() else "partly_off"


@dataclass
class Plan:
    """Sessions per (doctor, day), and the days a doctor has leave asked for but not decided."""

    sessions: dict = field(default_factory=lambda: defaultdict(list))
    leave_asked: set = field(default_factory=set)

    def on(self, staff_id, day: date) -> list[Session]:
        return sorted(self.sessions.get((staff_id, day), []), key=lambda s: s.start)


def _hours(start: datetime, end: datetime, zone) -> str:
    return f"{start.astimezone(zone):%H:%M}-{end.astimezone(zone):%H:%M}"


def _window(day: date, start: time | None, end: time | None, zone) -> tuple[datetime, datetime]:
    """A day (or part of it) on a facility's clock, as instants."""
    if start is None:
        return (
            datetime.combine(day, time.min, tzinfo=zone),
            datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone),
        )
    return datetime.combine(day, start, tzinfo=zone), datetime.combine(day, end, tzinfo=zone)


def _days(first: date, last: date):
    day = first
    while day <= last:
        yield day
        day += timedelta(days=1)


def _overlapping(rows, first: date, last: date, start="start_date", end="end_date"):
    return rows.filter(**{f"{start}__lte": last, f"{end}__gte": first})


def plan_for(*, staff_ids, first: date, last: date, department=None, details: bool) -> Plan:
    """Every session of these doctors from ``first`` to ``last`` (only in ``department`` when
    given), with what takes each off. ``details`` shows why a doctor is away (an OPD leave note);
    without it the reason reads only "Away"."""
    staff_ids = list(staff_ids)
    plan = Plan()
    if not staff_ids:
        return plan
    weekly = (
        DoctorSchedule.objects.filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=first),
            staff_id__in=staff_ids,
            is_active=True,
            valid_from__lte=last,
        )
        .select_related("department__facility")
        .order_by("start_time")
    )
    extras = ScheduleException.objects.filter(
        kind=ScheduleException.Kind.EXTRA_SESSION,
        status=ScheduleException.Status.ACTIVE,
        staff_id__in=staff_ids,
        start_date__gte=first,
        start_date__lte=last,
    ).select_related("department__facility")
    if department is not None:
        weekly = weekly.filter(department=department)
        extras = extras.filter(department=department)
    for schedule in weekly:
        zone = hospital_timezone(schedule.department.facility)
        for day in _days(max(first, schedule.valid_from), min(last, schedule.valid_until or last)):
            if day.weekday() != schedule.weekday:
                continue
            start, end = _window(day, schedule.start_time, schedule.end_time, zone)
            plan.sessions[(schedule.staff_id, day)].append(
                Session(
                    staff_id=schedule.staff_id,
                    department=schedule.department,
                    day=day,
                    start=start,
                    end=end,
                    slot_minutes=schedule.slot_minutes,
                    extra_bookings_allowed=schedule.extra_bookings_allowed,
                    source="weekly",
                    schedule_id=schedule.pk,
                    note=schedule.note,
                )
            )
    for extra in extras:
        zone = hospital_timezone(extra.department.facility)
        start, end = _window(extra.start_date, extra.start_time, extra.end_time, zone)
        plan.sessions[(extra.staff_id, extra.start_date)].append(
            Session(
                staff_id=extra.staff_id,
                department=extra.department,
                day=extra.start_date,
                start=start,
                end=end,
                slot_minutes=extra.slot_minutes,
                extra_bookings_allowed=extra.extra_bookings_allowed,
                source="extra",
                exception_id=extra.pk,
                note=extra.reason,
            )
        )
    _take_off(plan, staff_ids, first, last, details=details)
    _add_bookings(plan, staff_ids, first, last)
    return plan


def _add_bookings(plan: Plan, staff_ids, first: date, last: date) -> None:
    """Each session's appointments (one query; ``appointment_staff_day_idx``). Walk-ins take no
    slot (HIMS-OPD-003), so they are not counted here."""
    if not plan.sessions:
        return
    rows = (
        Appointment.objects.filter(
            staff_id__in=staff_ids,
            local_date__gte=first,
            local_date__lte=last,
            status__in=ACTIVE_STATUSES,
        )
        .exclude(source=Appointment.Source.WALK_IN)
        .values_list(
            "pk",
            "staff_id",
            "local_date",
            "schedule_id",
            "extra_session_id",
            "starts_at",
            "ends_at",
            "is_extra",
        )
    )
    for pk, staff_id, day, schedule_id, extra_id, start, end, is_extra in rows:
        for session in plan.sessions.get((staff_id, day), []):
            if (schedule_id and session.schedule_id == schedule_id) or (
                extra_id and session.exception_id == extra_id
            ):
                session.bookings.append(Booking(pk, start, end, is_extra))
                break


def _take_off(plan: Plan, staff_ids, first: date, last: date, *, details: bool) -> None:
    sessions = [s for found in plan.sessions.values() for s in found]
    status = dict(
        StaffMember.objects.filter(pk__in=staff_ids).values_list("pk", "employment_status")
    )
    postings = defaultdict(list)
    for (
        staff_id,
        department_id,
        valid_from,
        valid_until,
    ) in StaffDepartmentAssignment.objects.filter(
        Q(valid_until__isnull=True) | Q(valid_until__gte=first),
        staff_id__in=staff_ids,
        valid_from__lte=last,
    ).values_list("staff_id", "department_id", "valid_from", "valid_until"):
        postings[(staff_id, department_id)].append((valid_from, valid_until))
    rota_leave = defaultdict(list)
    for leave in _overlapping(
        LeaveRequest.objects.filter(
            staff_id__in=staff_ids,
            status__in=(LeaveRequest.Status.APPROVED, LeaveRequest.Status.REQUESTED),
        ),
        first,
        last,
    ):
        if leave.status == LeaveRequest.Status.REQUESTED:
            for day in _days(max(first, leave.start_date), min(last, leave.end_date)):
                plan.leave_asked.add((leave.staff_id, day))
        else:
            rota_leave[leave.staff_id].append(leave)
    away = defaultdict(list)
    for leave in _overlapping(
        ScheduleException.objects.filter(
            kind=ScheduleException.Kind.LEAVE,
            status=ScheduleException.Status.ACTIVE,
            staff_id__in=staff_ids,
        ),
        first,
        last,
    ):
        away[leave.staff_id].append(leave)
    facility_ids = {s.department.facility_id for s in sessions}
    holidays = list(
        _overlapping(
            ScheduleException.objects.filter(
                kind=ScheduleException.Kind.HOLIDAY,
                status=ScheduleException.Status.ACTIVE,
                facility_id__in=facility_ids,
            ),
            first,
            last,
        )
    )
    for session in sessions:
        whole = (session.start, session.end)
        working = status.get(session.staff_id)
        if working != StaffMember.EmploymentStatus.ACTIVE:
            label = StaffMember.EmploymentStatus(working).label.lower() if working else "unknown"
            session.take_off(*whole, "not_working", f"Not working ({label})")
        if session.department.status != Department.Status.ACTIVE:
            session.take_off(*whole, "department_closed", "The department is closed")
        posted = any(
            start <= session.day and (until is None or until >= session.day)
            for start, until in postings[(session.staff_id, session.department.pk)]
        )
        if not posted:
            session.take_off(*whole, "not_posted", f"Not posted in {session.department.name}")
        for leave in rota_leave[session.staff_id]:
            if leave.start_date <= session.day <= leave.end_date:
                session.take_off(*whole, "rota_leave", "On leave (approved on the Leave page)")
        for item in away[session.staff_id]:
            if item.start_date <= session.day <= item.end_date:
                start, end = _window(session.day, item.start_time, item.end_time, session.zone)
                reason = f"Away: {item.reason}" if details else "Away"
                session.take_off(start, end, "leave", reason, item.pk)
        for item in holidays:
            if not (item.start_date <= session.day <= item.end_date):
                continue
            if item.facility_id != session.department.facility_id:
                continue
            if item.department_id not in (None, session.department.pk):
                continue
            start, end = _window(session.day, item.start_time, item.end_time, session.zone)
            session.take_off(start, end, "holiday", f"Holiday: {item.reason}", item.pk)


def session_out(session: Session, *, with_slots: bool = False) -> dict:
    """A session for the API: its hours, what takes it off and (for one day) its open slots."""
    zone = session.zone
    now = timezone.now()
    slots = session.slots()
    return {
        "source": session.source,
        "schedule_id": session.schedule_id,
        "exception_id": session.exception_id,
        "staff_id": session.staff_id,
        "department_id": session.department.pk,
        "department_name": session.department.name,
        "facility_id": session.department.facility_id,
        "day": session.day,
        "starts_at": session.start,
        "ends_at": session.end,
        "hours": session.hours,
        "slot_minutes": session.slot_minutes,
        "extra_bookings_allowed": session.extra_bookings_allowed,
        "note": session.note,
        "status": session.status,
        "open_slots": len(slots),
        "booked": sum(1 for b in session.bookings if not b.is_extra),
        "extra_booked": session.extra_booked,
        "free_slots": sum(1 for start, end in slots if not session.is_taken(start, end)),
        "off": [
            {
                "kind": block.kind,
                "hours": _hours(block.start, block.end, zone),
                "reason": block.reason,
                "exception_id": block.exception_id,
            }
            for block in session.off
        ],
        "slots": [
            {
                "starts_at": start,
                "ends_at": end,
                "time": f"{start.astimezone(zone):%H:%M}",
                "is_past": start < now,
                "is_booked": session.is_taken(start, end),
            }
            for start, end in (slots if with_slots else [])
        ],
    }
