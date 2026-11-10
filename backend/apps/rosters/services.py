"""Rotas, on-call and leave: every rule lives here, used by the API and the admin console
(spec 4.3; HIMS-STAFF-012). See docs/architecture/data-architecture/rotas-and-leave.md."""

from datetime import date, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.access_control.catalog import P
from apps.audit.services import AuditAction, record_audit_event, snapshot
from apps.features.catalog import F
from apps.features.services import require_enabled
from apps.notifications.services import send_message
from apps.organizations.dates import hospital_timezone, hospital_today
from apps.staff.models import StaffDepartmentAssignment, StaffMember
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError

from .balances import balance_after
from .models import LeaveRequest, Shift, ShiftType

# Most days one "add shifts" request may cover (a month and a bit), and the longest leave.
MAX_SHIFT_DAYS = 62
MAX_LEAVE_DAYS = 366
# How far back leave may be recorded (e.g. sick leave reported on return).
LEAVE_BACKDATE_DAYS = 31
SHIFT_FIELDS = ["staff_id", "department_id", "shift_type_id", "on_date", "starts_at", "ends_at"]
LEAVE_FIELDS = ["staff_id", "department_id", "leave_type", "start_date", "end_date", "status"]
ACTIVE_LEAVE = (LeaveRequest.Status.REQUESTED, LeaveRequest.Status.APPROVED)


def _name(staff: StaffMember) -> str:
    return f"{staff.given_name} {staff.family_name}"


def _day(value: date) -> str:
    return value.strftime("%d %b %Y")


# --- Checks ------------------------------------------------------------------------------------


def posted_on(staff: StaffMember, department, day: date) -> bool:
    return StaffDepartmentAssignment.objects.filter(
        Q(valid_until__isnull=True) | Q(valid_until__gte=day),
        staff=staff,
        department=department,
        valid_from__lte=day,
    ).exists()


def approved_leave_on(staff: StaffMember, day: date) -> LeaveRequest | None:
    return LeaveRequest.objects.filter(
        staff=staff,
        status=LeaveRequest.Status.APPROVED,
        start_date__lte=day,
        end_date__gte=day,
    ).first()


def shift_problem(*, staff, department, shift_type, on_date: date):
    """Why this shift cannot be planned (None when it can), and its start and end."""
    start, end = shift_type.window(on_date, hospital_timezone(department.facility))
    if department.status != department.Status.ACTIVE:
        return "the department is not active", start, end
    if not shift_type.is_active:
        return f"the shift type {shift_type.name} is switched off", start, end
    if staff.employment_status != StaffMember.EmploymentStatus.ACTIVE:
        status = StaffMember.EmploymentStatus(staff.employment_status).label.lower()
        return f"{_name(staff)} is not working (employment status: {status})", start, end
    if end <= timezone.now():
        return "that shift is already over", start, end
    if not posted_on(staff, department, on_date):
        return f"{_name(staff)} is not posted in {department.name} on that day", start, end
    if approved_leave_on(staff, on_date):
        return f"{_name(staff)} is on approved leave that day", start, end
    clash = (
        Shift.objects.filter(
            staff=staff,
            status=Shift.Status.SCHEDULED,
            starts_at__lt=end,
            ends_at__gt=start,
        )
        .select_related("shift_type", "department")
        .first()
    )
    if clash:
        return (
            f"{_name(staff)} already has {clash.shift_type.name} in {clash.department.name} then",
            start,
            end,
        )
    return None, start, end


def _require_rotas(department, request=None) -> None:
    require_enabled(F.ROTAS, facility_id=department.facility_id, request=request)


# --- Shift types -------------------------------------------------------------------------------

SHIFT_TYPE_FIELDS = ["name", "kind", "start_time", "end_time", "is_active"]


@transaction.atomic
def create_shift_type(*, actor, code: str, request=None, **data) -> ShiftType:
    if ShiftType.objects.filter(code=code).exists():
        raise ConflictError("A shift type with this code already exists.", code="DUPLICATE_CODE")
    shift_type = ShiftType(code=code, is_custom=True, **data)
    shift_type.full_clean()
    shift_type.save()
    record_audit_event(
        action=AuditAction.SHIFT_TYPE_CREATED,
        resource_type="shift_type",
        resource_id=shift_type.pk,
        actor=actor,
        request=request,
        changes={"after": snapshot(shift_type, ["code", *SHIFT_TYPE_FIELDS])},
    )
    return shift_type


@transaction.atomic
def update_shift_type(*, actor, shift_type_id, version: int, request=None, **changes) -> ShiftType:
    """Planned shifts keep their times: a change applies to shifts planned afterwards."""
    from apps.audit.services import model_changes

    shift_type = lock_for_update(ShiftType, pk=shift_type_id, expected_version=version)
    before = snapshot(shift_type, SHIFT_TYPE_FIELDS)
    for field, value in changes.items():
        if field not in SHIFT_TYPE_FIELDS:
            raise ValueError(f"{field} is not updatable")
        setattr(shift_type, field, value)
    shift_type.full_clean()
    bump_version(shift_type)
    shift_type.save()
    record_audit_event(
        action=AuditAction.SHIFT_TYPE_UPDATED,
        resource_type="shift_type",
        resource_id=shift_type.pk,
        actor=actor,
        request=request,
        changes=model_changes(before, snapshot(shift_type, SHIFT_TYPE_FIELDS)),
    )
    return shift_type


# --- Shifts ------------------------------------------------------------------------------------


def _create_shift(*, actor, staff, department, shift_type, on_date, note, start, end, request):
    """Insert one shift; the database refuses an overlap that slipped past the checks (two
    planners at the same moment)."""
    try:
        with transaction.atomic():
            shift = Shift.objects.create(
                organization_id=department.organization_id,
                staff=staff,
                facility_id=department.facility_id,
                department=department,
                shift_type=shift_type,
                on_date=on_date,
                starts_at=start,
                ends_at=end,
                note=note,
                created_by=actor,
            )
    except IntegrityError:
        return None
    record_audit_event(
        action=AuditAction.SHIFT_ADDED,
        resource_type="shift",
        resource_id=shift.pk,
        facility_id=department.facility_id,
        actor=actor,
        request=request,
        changes={"after": snapshot(shift, [*SHIFT_FIELDS, "note"])},
    )
    return shift


@transaction.atomic
def add_shifts(
    *,
    actor,
    staff,
    department,
    shift_type,
    from_date: date,
    to_date: date,
    weekdays=None,
    note: str = "",
    request=None,
) -> tuple[list[Shift], list[dict]]:
    """Plan one shift type for one person on each chosen day. Days that cannot be planned are
    skipped and returned with the reason, so one problem day does not block the rest."""
    _require_rotas(department, request)
    if to_date < from_date:
        raise ConflictError("The last day cannot be before the first.", code="INVALID_DATES")
    if (to_date - from_date).days + 1 > MAX_SHIFT_DAYS:
        raise ConflictError(f"Plan at most {MAX_SHIFT_DAYS} days at a time.", code="TOO_MANY_DAYS")
    wanted = set(weekdays) if weekdays else None
    created, skipped = [], []
    day = from_date
    while day <= to_date:
        if wanted is None or day.weekday() in wanted:
            problem, start, end = shift_problem(
                staff=staff, department=department, shift_type=shift_type, on_date=day
            )
            shift = None
            if problem is None:
                shift = _create_shift(
                    actor=actor,
                    staff=staff,
                    department=department,
                    shift_type=shift_type,
                    on_date=day,
                    note=note,
                    start=start,
                    end=end,
                    request=request,
                )
                if shift is None:
                    problem = f"{_name(staff)} already has a shift then"
            if shift is not None:
                created.append(shift)
            else:
                skipped.append({"on_date": day, "person": _name(staff), "reason": problem})
        day += timedelta(days=1)
    return created, skipped


def _cancel(shift: Shift, *, actor, reason: str, request=None) -> None:
    before = snapshot(shift, ["status"])
    shift.status = Shift.Status.CANCELLED
    shift.cancelled_at = timezone.now()
    shift.cancelled_by = actor
    shift.cancel_reason = reason[:255]
    bump_version(shift)
    shift.save()
    record_audit_event(
        action=AuditAction.SHIFT_CANCELLED,
        resource_type="shift",
        resource_id=shift.pk,
        facility_id=shift.facility_id,
        actor=actor,
        request=request,
        reason=reason,
        changes={"before": before, "after": {"status": shift.status}},
    )


@transaction.atomic
def cancel_shift(*, actor, shift_id, version: int, reason: str, request=None) -> Shift:
    shift = lock_for_update(Shift, pk=shift_id, expected_version=version)
    _require_rotas(shift.department, request)
    if shift.status != Shift.Status.SCHEDULED:
        raise ConflictError("This shift is already cancelled.", code="ALREADY_CANCELLED")
    if shift.ends_at <= timezone.now():
        raise ConflictError(
            "This shift is already over; past shifts stay as they were.", code="SHIFT_OVER"
        )
    if not reason.strip():
        raise ConflictError("Give a reason.", code="REASON_REQUIRED")
    _cancel(shift, actor=actor, reason=reason.strip(), request=request)
    return shift


@transaction.atomic
def copy_week(
    *, actor, department, from_start: date, to_start: date, request=None
) -> tuple[list[Shift], list[dict]]:
    """Repeat one week's planned shifts in a later week, same weekdays. People who cannot work
    a copied day (leave, posting ended, already busy) are skipped and listed."""
    _require_rotas(department, request)
    offset = (to_start - from_start).days
    if offset <= 0 or offset % 7:
        raise ConflictError(
            "Copy into a later week starting on the same weekday.", code="INVALID_WEEK"
        )
    source = (
        Shift.objects.filter(
            department=department,
            status=Shift.Status.SCHEDULED,
            on_date__gte=from_start,
            on_date__lt=from_start + timedelta(days=7),
        )
        .select_related("staff", "shift_type")
        .order_by("on_date", "starts_at")
    )
    created, skipped = [], []
    for old in source:
        day = old.on_date + timedelta(days=offset)
        problem, start, end = shift_problem(
            staff=old.staff, department=department, shift_type=old.shift_type, on_date=day
        )
        shift = None
        if problem is None:
            shift = _create_shift(
                actor=actor,
                staff=old.staff,
                department=department,
                shift_type=old.shift_type,
                on_date=day,
                note=old.note,
                start=start,
                end=end,
                request=request,
            )
            problem = None if shift else f"{_name(old.staff)} already has a shift then"
        if shift is not None:
            created.append(shift)
        else:
            skipped.append({"on_date": day, "person": _name(old.staff), "reason": problem})
    return created, skipped


@transaction.atomic
def cancel_future_shifts(
    staff: StaffMember, *, reason: str, after: date | None = None, department=None
) -> int:
    """Shifts that can no longer happen (the person stopped working, or left the department)
    are cancelled, so the rota never shows someone who will not come. Returns how many."""
    rows = Shift.objects.filter(staff=staff, status=Shift.Status.SCHEDULED)
    rows = rows.filter(on_date__gt=after) if after else rows.filter(starts_at__gt=timezone.now())
    if department is not None:
        rows = rows.filter(department=department)
    count = 0
    for shift in rows.select_for_update():
        _cancel(shift, actor=None, reason=reason)
        count += 1
    return count


@transaction.atomic
def on_employment_status_changed(staff: StaffMember) -> None:
    """Called by the staff domain after suspension, termination or long leave."""
    if staff.employment_status == StaffMember.EmploymentStatus.ACTIVE:
        return
    status = StaffMember.EmploymentStatus(staff.employment_status).label.lower()
    cancel_future_shifts(staff, reason=f"Employment status changed to {status}")
    if staff.employment_status == StaffMember.EmploymentStatus.TERMINATED:
        today = hospital_today()
        for leave in LeaveRequest.objects.filter(
            staff=staff, status__in=ACTIVE_LEAVE, start_date__gt=today
        ).select_for_update():
            _close_leave(
                leave,
                status=LeaveRequest.Status.CANCELLED,
                actor=None,
                note="Employment ended",
                action=AuditAction.LEAVE_CANCELLED,
            )


# --- Leave -------------------------------------------------------------------------------------


def leave_approver_emails(department, *, exclude=()) -> list[str]:
    """Active people whose leave-approval grant covers this department."""
    return planner_emails(department, P.LEAVE_APPROVE, exclude=exclude)


def planner_emails(department, codename: str, *, exclude=()) -> list[str]:
    """Active people whose grant of this permission covers this department."""
    from apps.access_control.models import RoleAssignment

    now = timezone.now()
    rows = RoleAssignment.objects.filter(
        Q(valid_until__isnull=True) | Q(valid_until__gt=now),
        Q(facility__isnull=True)
        | Q(facility_id=department.facility_id, department__isnull=True)
        | Q(department_id=department.pk),
        revoked_at__isnull=True,
        valid_from__lte=now,
        user__is_active=True,
        role__role_permissions__permission__codename=codename,
    ).exclude(user_id__in=[u for u in exclude if u])
    return sorted(set(rows.values_list("user__email", flat=True)))


def _person_email(staff: StaffMember) -> list[str]:
    return [staff.user.email] if staff.user_id and staff.user.is_active else []


def _notify(leave: LeaveRequest, message: str, *, to, page: str, **values) -> None:
    link = f"{settings.HIMS_APP_BASE_URL.rstrip('/')}{page}"
    send_message(
        message,
        to=to,
        values={"period": _period(leave), "link": link, **values},
        related=("leave_request", leave.pk),
    )


def _period(leave: LeaveRequest) -> str:
    if leave.start_date == leave.end_date:
        return _day(leave.start_date)
    return f"{_day(leave.start_date)} to {_day(leave.end_date)} ({leave.days} days)"


def check_leave(*, staff, department, start_date: date, end_date: date) -> None:
    """Every rule for new leave; raises ConflictError with the reason."""
    if staff.employment_status not in (
        StaffMember.EmploymentStatus.ACTIVE,
        StaffMember.EmploymentStatus.ON_LEAVE,
    ):
        raise ConflictError(f"{_name(staff)} is not working here.", code="NOT_WORKING")
    if end_date < start_date:
        raise ConflictError("The last day cannot be before the first.", code="INVALID_DATES")
    if (end_date - start_date).days + 1 > MAX_LEAVE_DAYS:
        raise ConflictError(f"Ask for at most {MAX_LEAVE_DAYS} days at once.", code="TOO_LONG")
    today = hospital_today(department.facility)
    if start_date < today - timedelta(days=LEAVE_BACKDATE_DAYS):
        raise ConflictError(
            f"Leave can be recorded at most {LEAVE_BACKDATE_DAYS} days back.", code="TOO_FAR_BACK"
        )
    if not (posted_on(staff, department, start_date) or posted_on(staff, department, today)):
        raise ConflictError(
            f"{_name(staff)} is not posted in {department.name}.", code="NOT_POSTED"
        )
    overlap = LeaveRequest.objects.filter(
        staff=staff, status__in=ACTIVE_LEAVE, start_date__lte=end_date, end_date__gte=start_date
    ).first()
    if overlap:
        raise ConflictError(
            f"{_name(staff)} already has leave asked for or approved from "
            f"{_day(overlap.start_date)} to {_day(overlap.end_date)}.",
            code="LEAVE_OVERLAP",
        )


@transaction.atomic
def request_leave(
    *,
    actor,
    staff: StaffMember,
    department,
    leave_type: str,
    start_date: date,
    end_date: date,
    reason: str = "",
    request=None,
) -> LeaveRequest:
    """Ask for leave (the person) or record it for them (an approver). Either way it waits for
    a decision by someone else."""
    _require_rotas(department, request)
    check_leave(staff=staff, department=department, start_date=start_date, end_date=end_date)
    try:
        with transaction.atomic():
            leave = LeaveRequest.objects.create(
                organization_id=staff.organization_id,
                staff=staff,
                facility_id=department.facility_id,
                department=department,
                leave_type=leave_type,
                start_date=start_date,
                end_date=end_date,
                reason=reason.strip(),
                requested_by=actor,
            )
    except IntegrityError:
        raise ConflictError(
            f"{_name(staff)} already has leave asked for or approved on some of these days.",
            code="LEAVE_OVERLAP",
        ) from None
    record_audit_event(
        action=AuditAction.LEAVE_REQUESTED,
        resource_type="leave_request",
        resource_id=leave.pk,
        facility_id=leave.facility_id,
        actor=actor,
        request=request,
        changes={"after": snapshot(leave, LEAVE_FIELDS)},
        metadata={"on_behalf": staff.user_id != getattr(actor, "pk", None)},
    )
    _notify(
        leave,
        "rosters.leave_requested",
        to=leave_approver_emails(department, exclude=[getattr(actor, "pk", None), staff.user_id]),
        page="/leave",
        person=_name(staff),
        department=department.name,
        leave_type=leave.get_leave_type_display(),
    )
    return leave


def conflicting_shifts(leave: LeaveRequest):
    """Planned shifts the person would miss during this leave (not yet over)."""
    return (
        Shift.objects.filter(
            staff_id=leave.staff_id,
            status=Shift.Status.SCHEDULED,
            on_date__gte=leave.start_date,
            on_date__lte=leave.end_date,
            ends_at__gt=timezone.now(),
        )
        .select_related("shift_type", "department", "facility", "staff")
        .order_by("starts_at")
    )


def _close_leave(leave, *, status, actor, note, action, request=None, metadata=None) -> None:
    before = snapshot(leave, ["status"])
    leave.status = status
    if status == LeaveRequest.Status.CANCELLED:
        leave.cancelled_at = timezone.now()
        leave.cancelled_by = actor
        leave.cancel_reason = note[:255]
    else:
        leave.decided_at = timezone.now()
        leave.decided_by = actor
        leave.decision_note = note[:500]
    bump_version(leave)
    leave.save()
    record_audit_event(
        action=action,
        resource_type="leave_request",
        resource_id=leave.pk,
        facility_id=leave.facility_id,
        actor=actor,
        request=request,
        reason=note,
        changes={"before": before, "after": {"status": status}},
        metadata=metadata,
    )


def _not_own(leave: LeaveRequest, actor) -> None:
    if leave.staff.user_id and leave.staff.user_id == actor.pk:
        raise ConflictError(
            "You cannot decide your own leave; another approver has to.", code="SELF_DECISION"
        )


@transaction.atomic
def approve_leave(
    *,
    actor,
    leave_id,
    version: int,
    note: str = "",
    cancel_shifts: bool = False,
    allow_over_balance: bool = False,
    request=None,
) -> LeaveRequest:
    leave = lock_for_update(LeaveRequest, pk=leave_id, expected_version=version)
    _require_rotas(leave.department, request)
    _not_own(leave, actor)
    if leave.status != LeaveRequest.Status.REQUESTED:
        raise ConflictError("This leave has already been decided.", code="ALREADY_DECIDED")
    # One decision at a time for one person: two approvals cannot both spend the same days.
    StaffMember.objects.select_for_update().filter(pk=leave.staff_id).first()
    after = balance_after(leave)
    over_balance = after is not None and after < 0
    if over_balance and not allow_over_balance:
        raise ConflictError(
            f"This leave would leave {_name(leave.staff)} {-after} day(s) over their "
            f"{leave.get_leave_type_display().lower()} balance. Approve anyway only if the "
            "hospital allows it, and say why.",
            code="LEAVE_OVER_BALANCE",
        )
    if over_balance and not note.strip():
        raise ConflictError("Say why this leave goes over the balance.", code="REASON_REQUIRED")
    clashes = list(conflicting_shifts(leave))
    if clashes and not cancel_shifts:
        listed = "; ".join(
            f"{_day(s.on_date)} {s.shift_type.name} ({s.department.name})" for s in clashes[:5]
        )
        more = f" and {len(clashes) - 5} more" if len(clashes) > 5 else ""
        raise ConflictError(
            f"{_name(leave.staff)} has {len(clashes)} planned shift(s) during this leave: "
            f'{listed}{more}. Approve with "cancel those shifts", or move them first.',
            code="LEAVE_SHIFT_CONFLICT",
        )
    for shift in clashes:
        locked = Shift.objects.select_for_update().get(pk=shift.pk)
        _cancel(locked, actor=actor, reason="The person is on approved leave", request=request)
    _close_leave(
        leave,
        status=LeaveRequest.Status.APPROVED,
        actor=actor,
        note=note.strip(),
        action=AuditAction.LEAVE_APPROVED,
        request=request,
        metadata={"over_balance_by": -after} if over_balance else None,
    )
    _notify(
        leave,
        "rosters.leave_approved",
        to=_person_email(leave.staff),
        page="/my-schedule",
        leave_type=leave.get_leave_type_display().lower(),
        note=f"Note: {leave.decision_note}" if leave.decision_note else "",
    )
    return leave


@transaction.atomic
def reject_leave(*, actor, leave_id, version: int, note: str, request=None) -> LeaveRequest:
    leave = lock_for_update(LeaveRequest, pk=leave_id, expected_version=version)
    _require_rotas(leave.department, request)
    _not_own(leave, actor)
    if leave.status != LeaveRequest.Status.REQUESTED:
        raise ConflictError("This leave has already been decided.", code="ALREADY_DECIDED")
    if not note.strip():
        raise ConflictError("Say why it is refused.", code="REASON_REQUIRED")
    _close_leave(
        leave,
        status=LeaveRequest.Status.REJECTED,
        actor=actor,
        note=note.strip(),
        action=AuditAction.LEAVE_REJECTED,
        request=request,
    )
    _notify(
        leave,
        "rosters.leave_rejected",
        to=_person_email(leave.staff),
        page="/my-schedule",
        leave_type=leave.get_leave_type_display().lower(),
        reason=leave.decision_note,
    )
    return leave


@transaction.atomic
def cancel_leave(
    *, actor, leave_id, version: int, reason: str, as_approver: bool, request=None
) -> LeaveRequest:
    """The person may withdraw leave that has not started; an approver (permission checked by
    the caller) may cancel any leave that has not ended. Shifts are not put back by themselves:
    plan them again if needed."""
    leave = lock_for_update(LeaveRequest, pk=leave_id, expected_version=version)
    own = bool(leave.staff.user_id and leave.staff.user_id == actor.pk)
    if not (own or as_approver):
        raise ConflictError("This is not your leave.", code="NOT_YOURS")
    if leave.status not in ACTIVE_LEAVE:
        raise ConflictError("This leave is already closed.", code="ALREADY_CLOSED")
    today = hospital_today(leave.department.facility)
    if leave.end_date < today:
        raise ConflictError("This leave is already over.", code="LEAVE_OVER")
    if (
        own
        and not as_approver
        and leave.status == LeaveRequest.Status.APPROVED
        and leave.start_date <= today
    ):
        raise ConflictError(
            "Your leave has started; ask your head of department to end it.", code="LEAVE_STARTED"
        )
    if not reason.strip():
        raise ConflictError("Give a reason.", code="REASON_REQUIRED")
    _close_leave(
        leave,
        status=LeaveRequest.Status.CANCELLED,
        actor=actor,
        note=reason.strip(),
        action=AuditAction.LEAVE_CANCELLED,
        request=request,
    )
    if own:
        _notify(
            leave,
            "rosters.leave_withdrawn",
            to=leave_approver_emails(leave.department, exclude=[actor.pk]),
            page="/leave",
            person=_name(leave.staff),
        )
    else:
        _notify(
            leave,
            "rosters.leave_cancelled",
            to=_person_email(leave.staff),
            page="/my-schedule",
            person=_name(leave.staff),
            leave_type=leave.get_leave_type_display().lower(),
            reason=leave.cancel_reason,
        )
    return leave
