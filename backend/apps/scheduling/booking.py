"""Appointments: booking patients into doctors' OPD slots, moving and cancelling them (spec 4.6;
HIMS-OPD-002; P0 part 01 section 4, part 03 "Appointment"). Every rule lives here, used by the API
and the admin console. See docs/architecture/data-architecture/scheduling.md.

Bookings for one doctor are made one at a time (the doctor's staff row is locked), so extra
bookings over the slots (D11) are counted right. The database itself refuses two appointments of
one doctor at the same time (exclusion constraint): when two receptionists book the same slot at
the same moment, one succeeds and the other is told "This slot was just taken".

What a booking checks: the patient's record is in use (not merged), the slot is a free slot of
one of the doctor's sessions that day (not past, not taken off by leave, a holiday or anything
else, ADR-038), not more than 180 days ahead, and the patient is not booked elsewhere at that time.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services import AuditAction, record_audit_event, snapshot
from apps.organizations.dates import hospital_timezone, hospital_today
from apps.patients.models import Patient
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError

from . import availability
from .models import ACTIVE_STATUSES, Appointment
from .services import _lock_doctor, _name, _require_opd

MAX_AHEAD_DAYS = 180  # decisions log: appointments up to about six months ahead
APPOINTMENT_FIELDS = [
    "patient_id",
    "staff_id",
    "department_id",
    "starts_at",
    "ends_at",
    "local_date",
    "kind",
    "source",
    "is_extra",
    "status",
]
# Why the front desk cancels (moving an appointment records "rescheduled" itself, and a patient
# leaving the OPD queue "left before being seen", HIMS-OPD-003).
CANCEL_REASONS = [
    choice
    for choice in Appointment.CancelReason.choices
    if choice[0] not in (Appointment.CancelReason.RESCHEDULED, Appointment.CancelReason.LEFT_UNSEEN)
]


def _refuse(message: str, code: str):
    raise ConflictError(message, code=code)


def _when(moment: datetime, zone) -> str:
    return moment.astimezone(zone).strftime("%d %b %Y %H:%M")


@dataclass
class Check:
    """What a booking would hold, or why it cannot be made."""

    problem: str = ""
    code: str = ""
    session: availability.Session | None = None
    start: datetime | None = None
    end: datetime | None = None


def _place(staff, department, starts_at: datetime, zone) -> Check:
    """The session and slot this time falls on, among the doctor's sessions that day."""
    day = starts_at.astimezone(zone).date()
    plan = availability.plan_for(
        staff_ids=[staff.pk], first=day, last=day, department=department, details=False
    )
    for session in plan.on(staff.pk, day):
        if not session.start <= starts_at < session.end:
            continue
        for start, end in session.slots():
            if start == starts_at:
                return Check(session=session, start=start, end=end)
        off = next((b for b in session.off if b.start <= starts_at < b.end), None)
        why = f": {off.reason}" if off else ""
        return Check(
            f"{_when(starts_at, zone)} is not a free slot of this session{why}",
            "NOT_A_FREE_SLOT",
        )
    return Check(
        f"{_name(staff)} has no OPD session in {department.name} at {_when(starts_at, zone)}",
        "NOT_A_FREE_SLOT",
    )


def check_booking(
    *, patient, staff, department, starts_at: datetime, extra=False, moving=None
) -> Check:
    """Why this booking cannot be made (``problem`` empty when it can), with the place it would
    hold. ``moving`` is an appointment being moved here, which does not count against it.
    Read-only: ``book`` runs it again under the doctor's lock."""
    if patient.status == Patient.Status.MERGED:
        return Check(
            "This record was merged into another one: book on that record.", "PATIENT_MERGED"
        )
    zone = hospital_timezone(department.facility)
    if starts_at < timezone.now():
        return Check("This time has already passed.", "SLOT_IN_PAST")
    last = hospital_today(department.facility) + timedelta(days=MAX_AHEAD_DAYS)
    if starts_at.astimezone(zone).date() > last:
        return Check(f"Appointments can be booked at most {MAX_AHEAD_DAYS} days ahead.", "TOO_FAR")
    place = _place(staff, department, starts_at, zone)
    if place.problem:
        return place
    session = place.session
    taken = session.is_taken(place.start, place.end, ignore=getattr(moving, "pk", None))
    if taken and not extra:
        allowed = session.extra_bookings_allowed - session.extra_booked
        more = f" or book over the slots ({allowed} left)" if allowed > 0 else ""
        return Check(f"This slot is already booked: choose another{more}.", "SLOT_TAKEN")
    if extra and not taken:
        return Check("This slot is free: book it as a normal appointment.", "EXTRA_NOT_NEEDED")
    if extra and session.extra_booked >= session.extra_bookings_allowed:
        allowed = session.extra_bookings_allowed
        return Check(
            f"This session allows {allowed} booking(s) over its slots, all taken."
            if allowed
            else "This session allows no bookings over its slots.",
            "EXTRA_FULL",
        )
    clash = (
        Appointment.objects.filter(
            patient=patient,
            status__in=ACTIVE_STATUSES,
            starts_at__lt=place.end,
            ends_at__gt=place.start,
        )
        .exclude(pk=getattr(moving, "pk", None))
        .select_related("staff")
        .first()
    )
    if clash:
        return Check(
            f"The patient is already booked with {_name(clash.staff)} at "
            f"{_when(clash.starts_at, zone)}.",
            "PATIENT_ALREADY_BOOKED",
        )
    return place


def _audit(action, appointment, *, actor, request=None, reason="", changes=None, metadata=None):
    record_audit_event(
        action=action,
        resource_type="appointment",
        resource_id=appointment.pk,
        facility_id=appointment.facility_id,
        actor=actor,
        request=request,
        reason=reason,
        changes=changes or {"after": snapshot(appointment, APPOINTMENT_FIELDS)},
        metadata=metadata or {},
    )


@transaction.atomic
def book(
    *,
    actor,
    patient: Patient,
    staff,
    department,
    starts_at: datetime,
    kind: str = Appointment.Kind.NEW,
    source: str = Appointment.Source.FRONT_DESK,
    reason: str = "",
    extra: bool = False,
    rescheduled_from: Appointment | None = None,
    request=None,
) -> Appointment:
    """Book the patient into a free slot (or over the slots, when the session allows it)."""
    _require_opd(department.facility_id, request)
    staff = _lock_doctor(staff)
    check = check_booking(
        patient=patient, staff=staff, department=department, starts_at=starts_at, extra=extra
    )
    if check.problem:
        _refuse(check.problem, check.code)
    session = check.session
    try:
        with transaction.atomic():
            appointment = Appointment.objects.create(
                organization_id=department.organization_id,
                patient=patient,
                staff=staff,
                facility_id=department.facility_id,
                department=department,
                schedule_id=session.schedule_id,
                extra_session_id=session.exception_id,
                starts_at=check.start,
                ends_at=check.end,
                local_date=session.day,
                kind=kind,
                source=source,
                reason=" ".join(reason.split())[:200],
                is_extra=extra,
                rescheduled_from=rescheduled_from,
                booked_by=actor,
            )
    except IntegrityError:
        # Another booking for this time was saved a moment ago (the database's own rule).
        _refuse("This slot was just taken: choose another.", "SLOT_TAKEN")
    _audit(AuditAction.APPOINTMENT_BOOKED, appointment, actor=actor, request=request)
    return appointment


def _close(appointment: Appointment, *, reason: str, note: str, actor) -> None:
    appointment.status = Appointment.Status.CANCELLED
    appointment.cancel_reason = reason
    appointment.cancel_note = " ".join(note.split())[:255]
    appointment.cancelled_at = timezone.now()
    appointment.cancelled_by = actor
    bump_version(appointment)
    appointment.save()


@transaction.atomic
def reschedule(
    *,
    actor,
    appointment_id,
    version: int,
    starts_at: datetime,
    staff=None,
    department=None,
    extra: bool = False,
    note: str = "",
    request=None,
) -> Appointment:
    """Move a booked appointment to another slot (the same doctor unless another is given). The
    old one is cancelled as "moved" and links to the new one; both stay on record."""
    old = lock_for_update(Appointment, pk=appointment_id, expected_version=version)
    _require_opd(old.facility_id, request)
    if old.status != Appointment.Status.BOOKED:
        _refuse("Only a booked appointment can be moved.", "NOT_BOOKED")
    staff = staff or old.staff
    department = department or old.department
    if staff.pk == old.staff_id and starts_at == old.starts_at:
        _refuse("That is the time it already has.", "SAME_TIME")
    before = snapshot(old, ["staff_id", "department_id", "starts_at"])
    _close(old, reason=Appointment.CancelReason.RESCHEDULED, note=note, actor=actor)
    new = book(
        actor=actor,
        patient=old.patient,
        staff=staff,
        department=department,
        starts_at=starts_at,
        kind=old.kind,
        source=old.source,
        reason=old.reason,
        extra=extra,
        rescheduled_from=old,
        request=request,
    )
    _audit(
        AuditAction.APPOINTMENT_RESCHEDULED,
        old,
        actor=actor,
        request=request,
        reason=old.cancel_note,
        changes={
            "before": before,
            "after": snapshot(new, ["staff_id", "department_id", "starts_at"]),
        },
        metadata={"new_appointment": str(new.pk)},
    )
    return new


@transaction.atomic
def cancel(
    *, actor, appointment_id, version: int, reason: str, note: str = "", request=None
) -> Appointment:
    """Cancel a booked appointment, with why. Its day must not be over."""
    appointment = lock_for_update(Appointment, pk=appointment_id, expected_version=version)
    _require_opd(appointment.facility_id, request)
    if reason not in dict(CANCEL_REASONS):
        _refuse("Choose why it is cancelled.", "REASON_REQUIRED")
    if appointment.status != Appointment.Status.BOOKED:
        _refuse("Only a booked appointment can be cancelled.", "NOT_BOOKED")
    if appointment.local_date < hospital_today(appointment.department.facility):
        _refuse("This appointment's day is over: it stays on record as it was.", "ALREADY_OVER")
    _close(appointment, reason=reason, note=note, actor=actor)
    _audit(
        AuditAction.APPOINTMENT_CANCELLED,
        appointment,
        actor=actor,
        request=request,
        reason=appointment.cancel_note,
        changes={"before": {"status": "booked"}, "after": {"status": "cancelled"}},
        metadata={"cancel_reason": reason},
    )
    return appointment


def bookings_taken_off(sessions, exception_id) -> list:
    """Appointment ids in these sessions that an exception (leave, a holiday) now covers."""
    found = []
    for session in sessions:
        blocks = [b for b in session.off if b.exception_id == exception_id]
        for booking in session.bookings:
            if any(b.start < booking.end and booking.start < b.end for b in blocks):
                found.append(booking.appointment_id)
    return found
