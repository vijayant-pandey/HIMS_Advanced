"""Doctor OPD sessions and exceptions: every rule lives here, used by the API and the admin console
(spec 4.6; HIMS-OPD-001). See docs/architecture/data-architecture/scheduling.md.

Changes for one doctor are made one at a time (the staff row is locked), so two schedulers cannot
give the same doctor overlapping sessions; the database also refuses overlapping weekly sessions.
"""

from datetime import date, datetime, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import AuditAction, model_changes, record_audit_event, snapshot
from apps.facilities.models import Department, DepartmentHours
from apps.features.catalog import F
from apps.features.services import require_enabled
from apps.organizations.dates import hospital_timezone, hospital_today
from apps.rosters.models import LeaveRequest
from apps.rosters.services import posted_on
from apps.staff.models import StaffDepartmentAssignment, StaffMember
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError

from . import availability
from .models import MAX_EXTRA_BOOKINGS, DoctorSchedule, ScheduleException

# Who holds OPD sessions (P0 part 02: "must be a doctor with an active posting").
OPD_STAFF_TYPES = (StaffMember.StaffType.DOCTOR,)
MAX_EXCEPTION_DAYS = 366
MAX_AHEAD_DAYS = 400  # an extra session or a holiday at most about a year ahead
SCHEDULE_FIELDS = [
    "staff_id",
    "department_id",
    "weekday",
    "start_time",
    "end_time",
    "slot_minutes",
    "extra_bookings_allowed",
    "valid_from",
    "valid_until",
    "note",
]
CHANGEABLE = ("slot_minutes", "extra_bookings_allowed", "note")
EXCEPTION_FIELDS = [
    "kind",
    "staff_id",
    "facility_id",
    "department_id",
    "start_date",
    "end_date",
    "start_time",
    "end_time",
    "slot_minutes",
    "extra_bookings_allowed",
]


def _name(staff: StaffMember) -> str:
    return f"{staff.given_name} {staff.family_name}"


def _day(value: date) -> str:
    return value.strftime("%d %b %Y")


def _clock(start, end) -> str:
    return f"{start:%H:%M}-{end:%H:%M}"


def _minutes(start, end) -> int:
    return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)


def _refuse(message: str, code: str = "SESSION_NOT_POSSIBLE"):
    raise ConflictError(message, code=code)


def _require_opd(facility_id, request=None) -> None:
    require_enabled(F.OUTPATIENT, facility_id=facility_id, request=request)


def _lock_doctor(staff: StaffMember) -> StaffMember:
    return StaffMember.objects.select_for_update().get(pk=staff.pk)


# --- Checks ------------------------------------------------------------------------------------


def doctor_problem(staff: StaffMember, department: Department, day: date) -> str | None:
    """Why this person cannot hold OPD sessions in this department from this day."""
    if staff.staff_type not in OPD_STAFF_TYPES:
        return f"{_name(staff)} is not a doctor: only doctors hold OPD sessions"
    if staff.employment_status != StaffMember.EmploymentStatus.ACTIVE:
        status = StaffMember.EmploymentStatus(staff.employment_status).label.lower()
        return f"{_name(staff)} is not working (employment status: {status})"
    if department.status != Department.Status.ACTIVE:
        return f"{department.name} is not active"
    if not posted_on(staff, department, day):
        return f"{_name(staff)} is not posted in {department.name} on {_day(day)}"
    return None


def _slot_problem(start_time, end_time, slot_minutes: int, extra: int) -> str | None:
    if end_time <= start_time:
        return "The session must end after it starts, on the same day"
    if _minutes(start_time, end_time) < slot_minutes:
        return f"A {slot_minutes}-minute slot does not fit in {_clock(start_time, end_time)}"
    if extra > MAX_EXTRA_BOOKINGS:
        return f"At most {MAX_EXTRA_BOOKINGS} extra bookings per session"
    return None


def _hours_problem(department: Department, weekday: int, start_time, end_time) -> str | None:
    """A weekly session falls within the department's opening hours, when it has any."""
    if department.open_24_hours:
        return None
    hours = list(department.hours.all())
    if not hours:
        return None  # opening hours not entered: nothing to check against
    day = [h for h in hours if h.weekday == weekday]
    name = DepartmentHours.Weekday(weekday).label
    if not day:
        return f"{department.name} is closed on {name}s (opening hours, Departments page)"
    if any(h.opens_at <= start_time and end_time <= h.closes_at for h in day):
        return None
    open_hours = ", ".join(_clock(h.opens_at, h.closes_at) for h in day)
    return f"{department.name} is open {open_hours} on {name}s: the session must fit inside"


def _weekly_clash(staff, weekday, start_time, end_time, valid_from, valid_until, exclude=None):
    rows = DoctorSchedule.objects.filter(
        Q(valid_until__isnull=True) | Q(valid_until__gte=valid_from),
        staff=staff,
        weekday=weekday,
        is_active=True,
        start_time__lt=end_time,
        end_time__gt=start_time,
    ).select_related("department")
    if valid_until is not None:
        rows = rows.filter(valid_from__lte=valid_until)
    if exclude is not None:
        rows = rows.exclude(pk=exclude)
    return rows.first()


def schedule_problem(
    *,
    staff,
    department,
    weekday: int,
    start_time,
    end_time,
    slot_minutes: int,
    extra_bookings_allowed: int,
    valid_from: date,
    valid_until: date | None,
) -> str | None:
    """Why this weekly session cannot be added (None when it can)."""
    today = hospital_today(department.facility)
    if valid_from < today:
        return "A session cannot start in the past"
    if valid_until is not None and valid_until < valid_from:
        return "The last day cannot be before the first"
    problem = (
        doctor_problem(staff, department, valid_from)
        or _slot_problem(start_time, end_time, slot_minutes, extra_bookings_allowed)
        or _hours_problem(department, weekday, start_time, end_time)
    )
    if problem:
        return problem
    clash = _weekly_clash(staff, weekday, start_time, end_time, valid_from, valid_until)
    if clash:
        return (
            f"{_name(staff)} already has a session in {clash.department.name} "
            f"{_clock(clash.start_time, clash.end_time)} on that weekday"
        )
    return None


# --- Weekly sessions ---------------------------------------------------------------------------


def _audit_schedule(action, schedule, *, actor, request=None, reason="", changes=None):
    record_audit_event(
        action=action,
        resource_type="doctor_schedule",
        resource_id=schedule.pk,
        facility_id=schedule.facility_id,
        actor=actor,
        request=request,
        reason=reason,
        changes=changes or {"after": snapshot(schedule, SCHEDULE_FIELDS)},
    )


@transaction.atomic
def add_sessions(
    *,
    actor,
    staff: StaffMember,
    department: Department,
    weekdays,
    start_time,
    end_time,
    valid_from: date,
    valid_until: date | None = None,
    slot_minutes: int = 10,
    extra_bookings_allowed: int = 0,
    note: str = "",
    request=None,
) -> list[DoctorSchedule]:
    """The same session on one or more weekdays, e.g. Mon, Wed and Fri 09:00-13:00. All or none:
    one weekday that cannot be added stops the rest, with the reason."""
    _require_opd(department.facility_id, request)
    weekdays = sorted(set(weekdays))
    if not weekdays:
        _refuse("Choose at least one weekday.", "INVALID_WEEKDAYS")
    staff = _lock_doctor(staff)
    created = []
    for weekday in weekdays:
        problem = schedule_problem(
            staff=staff,
            department=department,
            weekday=weekday,
            start_time=start_time,
            end_time=end_time,
            slot_minutes=slot_minutes,
            extra_bookings_allowed=extra_bookings_allowed,
            valid_from=valid_from,
            valid_until=valid_until,
        )
        if problem:
            day = DepartmentHours.Weekday(weekday).label
            _refuse(f"{day}: {problem}.")
        try:
            with transaction.atomic():
                schedule = DoctorSchedule.objects.create(
                    organization_id=department.organization_id,
                    staff=staff,
                    facility_id=department.facility_id,
                    department=department,
                    weekday=weekday,
                    start_time=start_time,
                    end_time=end_time,
                    slot_minutes=slot_minutes,
                    extra_bookings_allowed=extra_bookings_allowed,
                    valid_from=valid_from,
                    valid_until=valid_until,
                    note=note.strip(),
                    created_by=actor,
                )
        except IntegrityError:
            _refuse(f"{_name(staff)} already has an OPD session at that time.", "SESSION_OVERLAP")
        _audit_schedule(AuditAction.DOCTOR_SCHEDULE_ADDED, schedule, actor=actor, request=request)
        created.append(schedule)
    return created


@transaction.atomic
def change_session(*, actor, schedule_id, version: int, request=None, **changes) -> DoctorSchedule:
    """Slot length, extra bookings and the note. Days and hours are changed by ending the session
    and adding a new one, so the old pattern stays on record."""
    schedule = lock_for_update(DoctorSchedule, pk=schedule_id, expected_version=version)
    _require_opd(schedule.facility_id, request)
    if not schedule.is_active or (
        schedule.valid_until is not None
        and schedule.valid_until < hospital_today(schedule.department.facility)
    ):
        _refuse("This session has ended: add a new one instead.", "SESSION_ENDED")
    before = snapshot(schedule, list(CHANGEABLE))
    for name, value in changes.items():
        if name not in CHANGEABLE:
            raise ValueError(f"{name} is not changeable")
        setattr(schedule, name, value.strip() if name == "note" else value)
    problem = _slot_problem(
        schedule.start_time,
        schedule.end_time,
        schedule.slot_minutes,
        schedule.extra_bookings_allowed,
    )
    if problem:
        _refuse(f"{problem}.")
    bump_version(schedule)
    schedule.save()
    _audit_schedule(
        AuditAction.DOCTOR_SCHEDULE_CHANGED,
        schedule,
        actor=actor,
        request=request,
        changes=model_changes(before, snapshot(schedule, list(CHANGEABLE))),
    )
    return schedule


def _end(schedule: DoctorSchedule, *, last_day: date, actor, reason: str, request=None) -> None:
    before = snapshot(schedule, ["valid_until", "is_active"])
    if last_day < schedule.valid_from:
        schedule.is_active = False  # it never ran: withdrawn
    else:
        schedule.valid_until = last_day
    schedule.ended_at = timezone.now()
    schedule.ended_by = actor
    schedule.end_reason = reason[:255]
    bump_version(schedule)
    schedule.save()
    _audit_schedule(
        AuditAction.DOCTOR_SCHEDULE_ENDED,
        schedule,
        actor=actor,
        request=request,
        reason=reason,
        changes={"before": before, "after": snapshot(schedule, ["valid_until", "is_active"])},
    )


@transaction.atomic
def end_session(
    *, actor, schedule_id, version: int, last_day: date, reason: str, request=None
) -> DoctorSchedule:
    """The session's last day (it runs that day). A day before its first day withdraws it."""
    schedule = lock_for_update(DoctorSchedule, pk=schedule_id, expected_version=version)
    _require_opd(schedule.facility_id, request)
    today = hospital_today(schedule.department.facility)
    if not reason.strip():
        _refuse("Say why the session ends.", "REASON_REQUIRED")
    if not schedule.is_active:
        _refuse("This session was already withdrawn.", "SESSION_ENDED")
    if schedule.valid_until is not None and schedule.valid_until < today:
        _refuse("This session has already ended.", "SESSION_ENDED")
    if last_day < today - timedelta(days=1):
        _refuse("The last day cannot be in the past: yesterday at the earliest.", "INVALID_DATES")
    if schedule.valid_until is not None and last_day > schedule.valid_until:
        _refuse(
            f"It already ends on {_day(schedule.valid_until)}: add a new session to go on.",
            "INVALID_DATES",
        )
    _end(schedule, last_day=last_day, actor=actor, reason=reason.strip(), request=request)
    return schedule


@transaction.atomic
def end_sessions_after(staff: StaffMember, *, after: date, reason: str, department=None) -> int:
    """Sessions that can no longer run after a day (the posting ended, the person left) end on
    that day, so the schedule never shows a doctor who will not come. Returns how many."""
    rows = DoctorSchedule.objects.filter(
        Q(valid_until__isnull=True) | Q(valid_until__gt=after), staff=staff, is_active=True
    )
    if department is not None:
        rows = rows.filter(department=department)
    count = 0
    for schedule in rows.select_for_update():
        _end(schedule, last_day=after, actor=None, reason=reason)
        count += 1
    extras = ScheduleException.objects.filter(
        staff=staff,
        kind=ScheduleException.Kind.EXTRA_SESSION,
        status=ScheduleException.Status.ACTIVE,
        start_date__gt=after,
    )
    if department is not None:
        extras = extras.filter(department=department)
    for extra in extras.select_for_update():
        _cancel(extra, actor=None, reason=reason)
        count += 1
    return count


def on_employment_status_changed(staff: StaffMember) -> None:
    """Called by the staff domain. Suspension or long leave only takes the sessions off (they
    come back on return); when employment ends, they end on the day before."""
    if staff.employment_status != StaffMember.EmploymentStatus.TERMINATED:
        return
    end_sessions_after(staff, after=hospital_today() - timedelta(days=1), reason="Employment ended")


# --- Exceptions --------------------------------------------------------------------------------


def _audit_exception(action, item, *, actor, request=None, reason="", changes=None):
    record_audit_event(
        action=action,
        resource_type="schedule_exception",
        resource_id=item.pk,
        facility_id=item.facility_id,
        actor=actor,
        request=request,
        reason=reason,
        changes=changes or {"after": snapshot(item, EXCEPTION_FIELDS)},
        metadata={"kind": item.kind},
    )


def _period_problem(item: ScheduleException, today: date) -> str | None:
    if item.end_date < item.start_date:
        return "The last day cannot be before the first"
    if item.start_date < today:
        return "It cannot start in the past"
    if item.start_date > today + timedelta(days=MAX_AHEAD_DAYS):
        return f"At most {MAX_AHEAD_DAYS} days ahead"
    if item.days > MAX_EXCEPTION_DAYS:
        return f"At most {MAX_EXCEPTION_DAYS} days at a time"
    if (item.start_time is None) != (item.end_time is None):
        return "Give both times, or neither for the whole day"
    if item.start_time is not None:
        if item.end_date != item.start_date:
            return "Times can only be given for one day"
        if item.end_time <= item.start_time:
            return "It must end after it starts"
    return None


def _extra_problem(item: ScheduleException) -> str | None:
    staff, department, day = item.staff, item.department, item.start_date
    if item.start_time is None:
        return "An extra session needs its hours"
    problem = doctor_problem(staff, department, day) or _slot_problem(
        item.start_time, item.end_time, item.slot_minutes, item.extra_bookings_allowed
    )
    if problem:
        return problem
    if LeaveRequest.objects.filter(
        staff=staff, status=LeaveRequest.Status.APPROVED, start_date__lte=day, end_date__gte=day
    ).exists():
        return f"{_name(staff)} is on approved leave that day"
    plan = availability.plan_for(staff_ids=[staff.pk], first=day, last=day, details=True)
    zone = hospital_timezone(department.facility)
    start = datetime.combine(day, item.start_time, tzinfo=zone)
    end = datetime.combine(day, item.end_time, tzinfo=zone)
    for session in plan.on(staff.pk, day):
        if session.start < end and start < session.end:
            return (
                f"{_name(staff)} already has a session in {session.department.name} "
                f"{session.hours} that day"
            )
    away = ScheduleException.objects.filter(
        staff=staff,
        kind=ScheduleException.Kind.LEAVE,
        status=ScheduleException.Status.ACTIVE,
        start_date__lte=day,
        end_date__gte=day,
    ).first()
    if away and (
        away.start_time is None
        or (away.start_time < item.end_time and item.start_time < away.end_time)
    ):
        return f"{_name(staff)} is recorded as away then"
    return None


def _leave_problem(item: ScheduleException) -> str | None:
    """A department records leave only for its own doctors (it takes off all their sessions)."""
    staff, department = item.staff, item.department
    if staff.staff_type not in OPD_STAFF_TYPES:
        return f"{_name(staff)} is not a doctor: only doctors hold OPD sessions"
    posted = StaffDepartmentAssignment.objects.filter(
        Q(valid_until__isnull=True) | Q(valid_until__gte=item.start_date),
        staff=staff,
        department=department,
        valid_from__lte=item.end_date,
    ).exists()
    if not posted:
        return f"{_name(staff)} is not posted in {department.name} on those days"
    return None


def new_exception(
    *,
    actor=None,
    kind: str,
    facility,
    start_date: date,
    end_date: date | None = None,
    staff: StaffMember | None = None,
    department: Department | None = None,
    start_time=None,
    end_time=None,
    slot_minutes: int | None = None,
    extra_bookings_allowed: int | None = None,
    reason: str = "",
) -> ScheduleException:
    """An unsaved exception with its kind's own shape: a holiday has no doctor; an extra session
    is one day with slots (10 minutes unless given)."""
    if kind == ScheduleException.Kind.HOLIDAY:
        staff = None
    if kind == ScheduleException.Kind.EXTRA_SESSION:
        end_date = start_date
        slot_minutes = slot_minutes or 10
        extra_bookings_allowed = extra_bookings_allowed or 0
    else:
        slot_minutes = extra_bookings_allowed = None
    return ScheduleException(
        organization_id=facility.organization_id,
        kind=kind,
        staff=staff,
        facility=facility,
        department=department,
        start_date=start_date,
        end_date=end_date or start_date,
        start_time=start_time,
        end_time=end_time,
        slot_minutes=slot_minutes,
        extra_bookings_allowed=extra_bookings_allowed,
        reason=reason.strip()[:255],
        created_by=actor,
    )


def exception_problem(item: ScheduleException) -> str | None:
    """Why this exception cannot be recorded (None when it can)."""
    if not item.reason:
        return "Say why (e.g. Conference, Diwali, Extra clinic for the health camp)"
    if item.kind != ScheduleException.Kind.HOLIDAY and (
        item.staff_id is None or item.department_id is None
    ):
        return "Choose the doctor and the department"
    if item.department_id and item.department.facility_id != item.facility_id:
        return "That department is in another facility"
    problem = _period_problem(item, hospital_today(item.facility))
    if problem is None and item.kind == ScheduleException.Kind.LEAVE:
        problem = _leave_problem(item)
    if problem is None and item.kind == ScheduleException.Kind.EXTRA_SESSION:
        problem = _extra_problem(item)
    return problem


@transaction.atomic
def add_exception(
    *,
    actor,
    kind: str,
    facility,
    start_date: date,
    end_date: date | None = None,
    staff: StaffMember | None = None,
    department: Department | None = None,
    start_time=None,
    end_time=None,
    slot_minutes: int | None = None,
    extra_bookings_allowed: int | None = None,
    reason: str,
    request=None,
) -> tuple[ScheduleException, list[availability.Session]]:
    """Record leave, a holiday or an extra session. Returns it with the sessions it takes off (a
    leave or a holiday), so the scheduler sees at once what is affected; booked patients are
    listed with appointments (HIMS-OPD-002)."""
    _require_opd(facility.pk, request)
    if staff is not None and kind != ScheduleException.Kind.HOLIDAY:
        staff = _lock_doctor(staff)
    item = new_exception(
        actor=actor,
        kind=kind,
        facility=facility,
        start_date=start_date,
        end_date=end_date,
        staff=staff,
        department=department,
        start_time=start_time,
        end_time=end_time,
        slot_minutes=slot_minutes,
        extra_bookings_allowed=extra_bookings_allowed,
        reason=reason,
    )
    problem = exception_problem(item)
    if problem:
        _refuse(f"{problem}.", "EXCEPTION_NOT_POSSIBLE")
    item.save()
    _audit_exception(AuditAction.SCHEDULE_EXCEPTION_ADDED, item, actor=actor, request=request)
    return item, affected_sessions(item)


def affected_sessions(item: ScheduleException) -> list[availability.Session]:
    """The sessions a leave or a holiday takes off (all or part of them)."""
    if item.kind == ScheduleException.Kind.EXTRA_SESSION:
        return []
    if item.kind == ScheduleException.Kind.LEAVE:
        staff_ids, department = [item.staff_id], None
    else:
        department = item.department
        rows = DoctorSchedule.objects.filter(facility_id=item.facility_id, is_active=True)
        extras = ScheduleException.objects.filter(
            facility_id=item.facility_id,
            kind=ScheduleException.Kind.EXTRA_SESSION,
            status=ScheduleException.Status.ACTIVE,
        )
        if department is not None:
            rows, extras = rows.filter(department=department), extras.filter(department=department)
        staff_ids = set(rows.values_list("staff_id", flat=True)) | set(
            extras.values_list("staff_id", flat=True)
        )
    plan = availability.plan_for(
        staff_ids=staff_ids,
        first=item.start_date,
        last=item.end_date,
        department=department,
        details=True,
    )
    found = []
    for sessions in plan.sessions.values():
        for session in sessions:
            if item.kind == ScheduleException.Kind.HOLIDAY and (
                session.department.facility_id != item.facility_id
            ):
                continue
            if any(block.exception_id == item.pk for block in session.off):
                found.append(session)
    return sorted(found, key=lambda s: (s.start, s.department.name))


def _cancel(item: ScheduleException, *, actor, reason: str, request=None) -> None:
    item.status = ScheduleException.Status.CANCELLED
    item.cancelled_at = timezone.now()
    item.cancelled_by = actor
    item.cancel_reason = reason[:255]
    bump_version(item)
    item.save()
    _audit_exception(
        AuditAction.SCHEDULE_EXCEPTION_CANCELLED,
        item,
        actor=actor,
        request=request,
        reason=reason,
        changes={"before": {"status": "active"}, "after": {"status": item.status}},
    )


@transaction.atomic
def cancel_exception(
    *, actor, exception_id, version: int, reason: str, request=None
) -> ScheduleException:
    """A leave, holiday or extra session that will not happen. Past ones stay as they were."""
    item = lock_for_update(ScheduleException, pk=exception_id, expected_version=version)
    _require_opd(item.facility_id, request)
    if not reason.strip():
        _refuse("Say why it is cancelled.", "REASON_REQUIRED")
    if item.status != ScheduleException.Status.ACTIVE:
        _refuse("This is already cancelled.", "ALREADY_CANCELLED")
    if item.end_date < hospital_today(item.facility):
        _refuse("This is already over: it stays on record as it was.", "ALREADY_OVER")
    _cancel(item, actor=actor, reason=reason.strip(), request=request)
    return item
