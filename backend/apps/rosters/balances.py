"""Leave balances and entitlements (HIMS-STAFF-013; spec 4.3). The hospital sets the numbers
(PO, 2026-11-08: fine for now). See docs/workflows/leave-balances.md.

A balance is never stored: it is worked out from the entitlement, carry-over, adjustments and
approved leave, so it cannot drift away from what really happened. A kind of leave with no
entitlement is not tracked, and behaves exactly as it did before.

An entitlement applies from its year until a later one replaces it. Rows for past years are not
changed, so last year's balances stay as they were.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from django.db import transaction

from apps.audit.services import AuditAction, model_changes, record_audit_event, snapshot
from apps.organizations.dates import hospital_today
from apps.organizations.models import Organization
from apps.staff.models import StaffMember
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError

from .models import LeaveBalanceAdjustment, LeaveEntitlement, LeaveRequest

ENTITLEMENT_FIELDS = ["days", "max_carry_over", "prorate_on_joining", "tracked"]
_APPROVED = LeaveRequest.Status.APPROVED
_REQUESTED = LeaveRequest.Status.REQUESTED


@dataclass(frozen=True)
class Balance:
    leave_type: str
    label: str
    year: int
    year_label: str
    entitled: int
    carried_in: int
    adjusted: int
    taken: int
    waiting: int
    remaining: int


def start_month() -> int:
    organization = Organization.objects.only("leave_year_start_month").first()
    return organization.leave_year_start_month if organization else 1


def leave_year_of(day: date, month: int) -> int:
    """A leave year is named after the calendar year it starts in."""
    return day.year if day.month >= month else day.year - 1


def year_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year + 1, month, 1) - timedelta(days=1)


def year_label(year: int, month: int) -> str:
    return str(year) if month == 1 else f"{year}-{str(year + 1)[-2:]}"


def current_year(month: int | None = None) -> int:
    month = month or start_month()
    return leave_year_of(hospital_today(), month)


def _effective(rows: list[LeaveEntitlement], year: int) -> LeaveEntitlement | None:
    """The row in force that year (rows are in year order); None when not tracked then."""
    found = None
    for row in rows:
        if row.from_year > year:
            break
        found = row
    return found if found is not None and found.tracked else None


def _days_in(leave: LeaveRequest, first: date, last: date) -> int:
    start, end = max(leave.start_date, first), min(leave.end_date, last)
    return max(0, (end - start).days + 1)


def _entitled(row: LeaveEntitlement, staff: StaffMember, first: date, last: date) -> int:
    """A person who joined during the year gets a share by whole months, if the hospital says so
    (the month they joined in counts; half a day rounds up)."""
    if not row.prorate_on_joining or staff.joined_on <= first:
        return row.days
    months = (last.year - staff.joined_on.year) * 12 + last.month - staff.joined_on.month + 1
    return int(row.days * months / 12 + 0.5)


def _entitlements() -> dict[str, list[LeaveEntitlement]]:
    rows = defaultdict(list)
    for row in LeaveEntitlement.objects.order_by("leave_type", "from_year"):
        rows[row.leave_type].append(row)
    return rows


def balances_for(staff_list, *, year: int | None = None) -> dict:
    """{staff id: [Balance for each kind of leave tracked that year]}. One pass over all the
    people, so a whole department costs the same few queries as one person."""
    month = start_month()
    year = current_year(month) if year is None else year
    by_type = _entitlements()
    result: dict = {staff.pk: [] for staff in staff_list}
    if not by_type or not result:
        return result
    earliest = min(rows[0].from_year for rows in by_type.values())
    leave_rows = defaultdict(list)
    for leave in LeaveRequest.objects.filter(
        staff_id__in=result,
        status__in=[_APPROVED, _REQUESTED],
        leave_type__in=by_type,
        end_date__gte=date(earliest, month, 1),
    ):
        leave_rows[(leave.staff_id, leave.leave_type)].append(leave)
    adjustments = defaultdict(int)
    for row in LeaveBalanceAdjustment.objects.filter(staff_id__in=result):
        adjustments[(row.staff_id, row.leave_type, row.leave_year)] += row.days
    labels = dict(LeaveRequest.LeaveType.choices)
    for staff in staff_list:
        for leave_type, rows in by_type.items():
            balance = _balance(
                staff,
                leave_type,
                labels[leave_type],
                rows,
                leave_rows[(staff.pk, leave_type)],
                adjustments,
                year,
                month,
            )
            if balance is not None:
                result[staff.pk].append(balance)
    return result


def _balance(staff, leave_type, label, rows, leaves, adjustments, year, month) -> Balance | None:
    """Walks from the first year this kind of leave was tracked for this person, because each
    year's carry-over depends on the year before."""
    joined = leave_year_of(staff.joined_on, month)
    if _effective(rows, year) is None or joined > year:
        return None
    carried_in = 0
    balance = None
    for y in range(max(rows[0].from_year, joined), year + 1):
        row = _effective(rows, y)
        if row is None:  # tracking was switched off that year: nothing carries through it
            carried_in = 0
            continue
        first, last = year_bounds(y, month)
        entitled = _entitled(row, staff, first, last)
        adjusted = adjustments[(staff.pk, leave_type, y)]
        taken = sum(_days_in(x, first, last) for x in leaves if x.status == _APPROVED)
        waiting = sum(_days_in(x, first, last) for x in leaves if x.status == _REQUESTED)
        remaining = entitled + carried_in + adjusted - taken
        balance = Balance(
            leave_type=leave_type,
            label=label,
            year=y,
            year_label=year_label(y, month),
            entitled=entitled,
            carried_in=carried_in,
            adjusted=adjusted,
            taken=taken,
            waiting=waiting,
            remaining=remaining,
        )
        carried_in = min(row.max_carry_over, max(0, remaining))
    return balance


def balance_after(leave: LeaveRequest) -> int | None:
    """What would be left if this leave were approved: the lowest figure across the leave years
    it touches. None when this kind of leave is not tracked in any of them."""
    month = start_month()
    lowest = None
    for year in range(
        leave_year_of(leave.start_date, month), leave_year_of(leave.end_date, month) + 1
    ):
        rows = balances_for([leave.staff], year=year)[leave.staff_id]
        balance = next((b for b in rows if b.leave_type == leave.leave_type), None)
        if balance is None:
            continue
        after = balance.remaining - _days_in(leave, *year_bounds(year, month))
        lowest = after if lowest is None else min(lowest, after)
    return lowest


# --- Entitlements and adjustments --------------------------------------------------------------


@transaction.atomic
def create_entitlement(
    *,
    actor,
    leave_type: str,
    from_year: int,
    days: int,
    max_carry_over: int = 0,
    prorate_on_joining: bool = True,
    tracked: bool = True,
    request=None,
) -> LeaveEntitlement:
    if from_year < current_year():
        raise ConflictError(
            "An entitlement starts this leave year or later, so past balances stay as they were. "
            "For balances brought from before, use an adjustment.",
            code="PAST_YEAR",
        )
    if LeaveEntitlement.objects.filter(leave_type=leave_type, from_year=from_year).exists():
        raise ConflictError(
            "This kind of leave already has an entitlement from that year. Change that one.",
            code="DUPLICATE_ENTITLEMENT",
        )
    row = LeaveEntitlement(
        leave_type=leave_type,
        from_year=from_year,
        days=days,
        max_carry_over=max_carry_over,
        prorate_on_joining=prorate_on_joining,
        tracked=tracked,
        updated_by=actor,
    )
    row.full_clean()
    row.save()
    record_audit_event(
        action=AuditAction.LEAVE_ENTITLEMENT_CREATED,
        resource_type="leave_entitlement",
        resource_id=row.pk,
        actor=actor,
        request=request,
        changes={"after": snapshot(row, ["leave_type", "from_year", *ENTITLEMENT_FIELDS])},
    )
    return row


@transaction.atomic
def update_entitlement(*, actor, entitlement_id, version: int, request=None, **changes):
    row = lock_for_update(LeaveEntitlement, pk=entitlement_id, expected_version=version)
    if row.from_year < current_year():
        raise ConflictError(
            "This entitlement started in an earlier year, and changing it would rewrite past "
            "balances. Add a new one from this year.",
            code="ENTITLEMENT_IN_USE",
        )
    before = snapshot(row, ENTITLEMENT_FIELDS)
    for field, value in changes.items():
        if field not in ENTITLEMENT_FIELDS:
            raise ValueError(f"{field} is not updatable")
        setattr(row, field, value)
    row.updated_by = actor
    row.full_clean()
    bump_version(row)
    row.save()
    record_audit_event(
        action=AuditAction.LEAVE_ENTITLEMENT_UPDATED,
        resource_type="leave_entitlement",
        resource_id=row.pk,
        actor=actor,
        request=request,
        changes=model_changes(before, snapshot(row, ENTITLEMENT_FIELDS)),
    )
    return row


@transaction.atomic
def adjust_balance(
    *,
    actor,
    staff: StaffMember,
    leave_type: str,
    leave_year: int,
    days: int,
    reason: str,
    request=None,
) -> LeaveBalanceAdjustment:
    """Add or take away days: a balance brought from before HIMS, a compensatory day, a
    correction. Append-only: a wrong adjustment is corrected by another one."""
    check_adjustment(
        actor=actor,
        staff=staff,
        leave_type=leave_type,
        leave_year=leave_year,
        days=days,
        reason=reason,
    )
    row = LeaveBalanceAdjustment(
        staff=staff,
        leave_type=leave_type,
        leave_year=leave_year,
        days=days,
        reason=reason.strip(),
        created_by=actor,
    )
    row.full_clean()
    row.save()
    record_audit_event(
        action=AuditAction.LEAVE_BALANCE_ADJUSTED,
        resource_type="leave_balance_adjustment",
        resource_id=row.pk,
        actor=actor,
        request=request,
        reason=row.reason,
        metadata={
            "staff_member_id": str(staff.pk),
            "leave_type": leave_type,
            "leave_year": leave_year,
            "days": days,
        },
    )
    return row


def check_adjustment(
    *, actor, staff: StaffMember, leave_type: str, leave_year: int, days: int, reason: str
) -> None:
    """Every rule for an adjustment; raises ConflictError with the reason."""
    if staff.user_id and staff.user_id == getattr(actor, "pk", None):
        raise ConflictError(
            "You cannot adjust your own leave balance; someone else has to.", code="SELF_ADJUST"
        )
    if days == 0:
        raise ConflictError("Add or take away at least one day.", code="NO_CHANGE")
    if not reason.strip():
        raise ConflictError("Give a reason.", code="REASON_REQUIRED")
    if _effective(_entitlements()[leave_type], leave_year) is None:
        raise ConflictError(
            "This kind of leave has no entitlement that year, so it has no balance to adjust.",
            code="NOT_TRACKED",
        )
