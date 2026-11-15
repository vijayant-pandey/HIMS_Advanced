"""The day of the visit: check-in with token numbers, walk-ins, the OPD queue and the patients who
did not come (spec 4.6; HIMS-OPD-003; P0 part 01 section 4, part 03 "Appointment", D10, D12).
Every rule lives here, used by the API, the admin console and the no-show job. See
docs/architecture/data-architecture/scheduling.md, part 3.

Tokens: each doctor's day has its own numbers 1, 2, 3..., given in the order patients arrive (a
booked patient at check-in, a walk-in when they come). They are given under a lock on the
doctor's staff row, and the database refuses a number twice (``appointment_one_token``).

A walk-in takes no slot: it is checked in at once, in the doctor's session today (the one running,
else the next, else the last), and waits for its token like everyone else. The queue moves with
**Call next** (the lowest waiting token goes in to the doctor; whoever was with the doctor is then
seen) and **Seen**. Until outpatient visits exist (HIMS-CLIN-001), the front desk moves the queue;
then the doctor's start and finish of the visit do.

A booked patient not checked in when the session ends is marked "did not come" by a job every 15
minutes (``mark_no_shows``; safe to run again: only booked appointments of ended sessions). The
front desk may also mark it once the time has passed, undo it before the session ends, or check in
a patient who came late the same day.
"""

from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from apps.audit.services import AuditAction
from apps.organizations.dates import hospital_timezone, hospital_today
from apps.patients.models import Patient
from common.concurrency import bump_version, lock_for_update

from . import availability
from .booking import _audit, _refuse, _when
from .models import Appointment
from .selectors import _why_off
from .services import _lock_doctor, _name, _require_opd

WAITING = (Appointment.Status.CHECKED_IN, Appointment.Status.IN_CONSULTATION)
NO_SHOW_BATCH = 500  # per run of the job; the next run (15 minutes later) takes the rest


def _today(appointment: Appointment):
    return hospital_today(appointment.facility)


def session_end(appointment: Appointment) -> datetime:
    """When the appointment's session ends that day, on the facility's clock."""
    source = appointment.schedule or appointment.extra_session
    zone = hospital_timezone(appointment.facility)
    return datetime.combine(appointment.local_date, source.end_time, tzinfo=zone)


def _next_token(staff_id, day) -> int:
    """The doctor's next token for the day (call with the doctor's row locked)."""
    last = Appointment.objects.filter(
        staff_id=staff_id, local_date=day, token_number__isnull=False
    ).aggregate(last=Max("token_number"))["last"]
    return (last or 0) + 1


def _lock(appointment_id, version: int) -> Appointment:
    appointment = lock_for_update(Appointment, pk=appointment_id, expected_version=version)
    _require_opd(appointment.facility_id)
    return appointment


def _save(appointment: Appointment) -> None:
    bump_version(appointment)
    appointment.save()


def _move(action, appointment, before: str, *, actor, request=None, reason="", metadata=None):
    _audit(
        action,
        appointment,
        actor=actor,
        request=request,
        reason=reason,
        changes={"before": {"status": before}, "after": {"status": appointment.status}},
        metadata=metadata,
    )


@transaction.atomic
def check_in(*, actor, appointment_id, version: int, request=None) -> Appointment:
    """The patient has come: give the doctor's next token for the day. A booked appointment on its
    day (or one marked "did not come" that day: the patient came late)."""
    appointment = _lock(appointment_id, version)
    before = appointment.status
    if before in WAITING or before == Appointment.Status.COMPLETED:
        _refuse(f"Already checked in: token {appointment.token_number}.", "ALREADY_CHECKED_IN")
    if before not in (Appointment.Status.BOOKED, Appointment.Status.NO_SHOW):
        _refuse("Only a booked appointment can be checked in.", "NOT_BOOKED")
    if appointment.local_date != _today(appointment):
        _refuse(
            f"Patients are checked in on the day of their appointment "
            f"({appointment.local_date:%d %b %Y}).",
            "NOT_TODAY",
        )
    staff = _lock_doctor(appointment.staff)
    plan = availability.plan_for(
        staff_ids=[staff.pk],
        first=appointment.local_date,
        last=appointment.local_date,
        department=appointment.department,
        details=False,
    )
    why = _why_off(appointment, plan.on(staff.pk, appointment.local_date))
    if why:
        _refuse(
            f"{_name(staff)} is not seeing patients at this time ({why}): move the appointment.",
            "SESSION_OFF",
        )
    appointment.status = Appointment.Status.CHECKED_IN
    appointment.token_number = _next_token(staff.pk, appointment.local_date)
    appointment.checked_in_at = timezone.now()
    appointment.checked_in_by = actor
    _save(appointment)
    _move(
        AuditAction.APPOINTMENT_CHECKED_IN,
        appointment,
        before,
        actor=actor,
        request=request,
        metadata={"token": appointment.token_number, "late": before == "no_show"},
    )
    return appointment


def _walk_in_session(staff, department, day, now):
    """The doctor's session today that a walk-in joins: the one running now, else the next one,
    else the last one (the doctor may still be seeing patients). None when there is none."""
    plan = availability.plan_for(
        staff_ids=[staff.pk], first=day, last=day, department=department, details=False
    )
    sessions = [s for s in plan.on(staff.pk, day) if s.status != "off"]
    if not sessions:
        return None
    running = [s for s in sessions if s.start <= now < s.end]
    coming = [s for s in sessions if s.start > now]
    return (running or coming or sessions[-1:])[0]


@transaction.atomic
def walk_in(
    *,
    actor,
    patient: Patient,
    staff,
    department,
    kind: str = Appointment.Kind.NEW,
    reason: str = "",
    request=None,
) -> Appointment:
    """A patient without an appointment: checked in at once with the doctor's next token."""
    _require_opd(department.facility_id, request)
    if patient.status == Patient.Status.MERGED:
        _refuse("This record was merged into another one: use that record.", "PATIENT_MERGED")
    staff = _lock_doctor(staff)
    facility = department.facility
    day = hospital_today(facility)
    now = timezone.now()
    session = _walk_in_session(staff, department, day, now)
    if session is None:
        _refuse(
            f"{_name(staff)} has no OPD session in {department.name} today.", "NO_SESSION_TODAY"
        )
    waiting = (
        Appointment.objects.filter(patient=patient, local_date=day, status__in=WAITING)
        .select_related("staff")
        .first()
    )
    if waiting:
        _refuse(
            f"The patient is already waiting for {_name(waiting.staff)} (token "
            f"{waiting.token_number}).",
            "ALREADY_WAITING",
        )
    booked = Appointment.objects.filter(
        patient=patient, staff=staff, local_date=day, status=Appointment.Status.BOOKED
    ).first()
    if booked:
        zone = hospital_timezone(facility)
        _refuse(
            f"The patient has an appointment with {_name(staff)} at "
            f"{booked.starts_at.astimezone(zone):%H:%M} today: check them in instead.",
            "HAS_APPOINTMENT",
        )
    starts_at = now.replace(second=0, microsecond=0)
    appointment = Appointment.objects.create(
        organization_id=department.organization_id,
        patient=patient,
        staff=staff,
        facility_id=department.facility_id,
        department=department,
        schedule_id=session.schedule_id,
        extra_session_id=session.exception_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=session.slot_minutes),
        local_date=day,
        kind=kind,
        source=Appointment.Source.WALK_IN,
        status=Appointment.Status.CHECKED_IN,
        reason=" ".join(reason.split())[:200],
        booked_by=actor,
        token_number=_next_token(staff.pk, day),
        checked_in_at=now,
        checked_in_by=actor,
    )
    _audit(
        AuditAction.APPOINTMENT_WALK_IN,
        appointment,
        actor=actor,
        request=request,
        metadata={"token": appointment.token_number},
    )
    return appointment


def _finish(appointment: Appointment, *, actor, request=None) -> None:
    appointment.status = Appointment.Status.COMPLETED
    appointment.seen_at = timezone.now()
    _save(appointment)
    _move(
        AuditAction.APPOINTMENT_SEEN,
        appointment,
        Appointment.Status.IN_CONSULTATION,
        actor=actor,
        request=request,
    )


@transaction.atomic
def call_next(*, actor, staff, department, request=None) -> dict:
    """Call the lowest waiting token of this doctor in this department in to the doctor; whoever
    was with the doctor is then seen. Returns ``{"called": ..., "seen": [...]}``."""
    _require_opd(department.facility_id, request)
    staff = _lock_doctor(staff)
    day = hospital_today(department.facility)
    seen = list(
        Appointment.objects.select_for_update().filter(
            staff=staff, local_date=day, status=Appointment.Status.IN_CONSULTATION
        )
    )
    waiting = (
        Appointment.objects.select_for_update()
        .filter(
            staff=staff,
            local_date=day,
            department=department,
            status=Appointment.Status.CHECKED_IN,
        )
        .order_by("token_number")
        .first()
    )
    if waiting is None and not seen:
        _refuse(f"Nobody is waiting for {_name(staff)}.", "NONE_WAITING")
    for appointment in seen:
        _finish(appointment, actor=actor, request=request)
    if waiting is not None:
        waiting.status = Appointment.Status.IN_CONSULTATION
        waiting.called_at = timezone.now()
        _save(waiting)
        _move(
            AuditAction.APPOINTMENT_CALLED,
            waiting,
            Appointment.Status.CHECKED_IN,
            actor=actor,
            request=request,
            metadata={"token": waiting.token_number},
        )
    return {"called": waiting, "seen": seen}


@transaction.atomic
def mark_seen(*, actor, appointment_id, version: int, request=None) -> Appointment:
    """The doctor is done with the patient now with them."""
    appointment = _lock(appointment_id, version)
    if appointment.status != Appointment.Status.IN_CONSULTATION:
        _refuse("Only the patient with the doctor can be marked seen.", "NOT_WITH_DOCTOR")
    _finish(appointment, actor=actor, request=request)
    return appointment


@transaction.atomic
def left_unseen(*, actor, appointment_id, version: int, note: str = "", request=None):
    """A waiting patient left before being seen. Kept on record with their token."""
    appointment = _lock(appointment_id, version)
    if appointment.status != Appointment.Status.CHECKED_IN:
        _refuse("Only a waiting patient can leave the queue.", "NOT_WAITING")
    appointment.status = Appointment.Status.CANCELLED
    appointment.cancel_reason = Appointment.CancelReason.LEFT_UNSEEN
    appointment.cancel_note = " ".join(note.split())[:255]
    appointment.cancelled_at = timezone.now()
    appointment.cancelled_by = actor
    _save(appointment)
    _move(
        AuditAction.APPOINTMENT_LEFT,
        appointment,
        Appointment.Status.CHECKED_IN,
        actor=actor,
        request=request,
        reason=appointment.cancel_note,
    )
    return appointment


def _no_show(appointment: Appointment, *, actor, request=None, by: str) -> None:
    appointment.status = Appointment.Status.NO_SHOW
    _save(appointment)
    _move(
        AuditAction.APPOINTMENT_NO_SHOW,
        appointment,
        Appointment.Status.BOOKED,
        actor=actor,
        request=request,
        metadata={"by": by},
    )


@transaction.atomic
def mark_no_show(*, actor, appointment_id, version: int, request=None) -> Appointment:
    """The front desk marks a booked patient as not come, once their time has passed."""
    appointment = _lock(appointment_id, version)
    if appointment.status != Appointment.Status.BOOKED:
        _refuse("Only a booked appointment can be marked as not come.", "NOT_BOOKED")
    if appointment.starts_at > timezone.now():
        zone = hospital_timezone(appointment.facility)
        _refuse(f"Its time has not come yet ({_when(appointment.starts_at, zone)}).", "NOT_YET")
    _no_show(appointment, actor=actor, request=request, by="front_desk")
    return appointment


@transaction.atomic
def undo_no_show(*, actor, appointment_id, version: int, request=None) -> Appointment:
    """Marked "did not come" by mistake: booked again, the same day and before the session ends
    (after it, check the patient in if they came)."""
    appointment = _lock(appointment_id, version)
    if appointment.status != Appointment.Status.NO_SHOW:
        _refuse("Only an appointment marked as not come can be undone.", "NOT_NO_SHOW")
    if appointment.local_date != _today(appointment) or session_end(appointment) <= (
        timezone.now()
    ):
        _refuse("Its session is over: if the patient came, check them in instead.", "SESSION_OVER")
    appointment.status = Appointment.Status.BOOKED
    try:
        with transaction.atomic():
            _save(appointment)
    except IntegrityError:
        _refuse("Its slot was booked for someone else.", "SLOT_TAKEN")
    _move(
        AuditAction.APPOINTMENT_NO_SHOW_UNDONE,
        appointment,
        Appointment.Status.NO_SHOW,
        actor=actor,
        request=request,
    )
    return appointment


def mark_no_shows(now: datetime | None = None) -> int:
    """The job: booked appointments whose session has ended are marked "did not come" (D12).
    Safe to run again; at most ``NO_SHOW_BATCH`` a run (``appointment_booked_end_idx``: a slot
    ends before its session does)."""
    now = now or timezone.now()
    rows = (
        Appointment.objects.filter(status=Appointment.Status.BOOKED, ends_at__lte=now)
        .select_related("schedule", "extra_session", "facility")
        .order_by("ends_at")[:NO_SHOW_BATCH]
    )
    marked = 0
    for row in rows:
        if session_end(row) > now:
            continue
        with transaction.atomic():
            appointment = (
                Appointment.objects.select_for_update(of=("self",))
                .select_related("schedule", "extra_session", "facility")
                .filter(pk=row.pk, status=Appointment.Status.BOOKED)
                .first()
            )
            if appointment is None:
                continue  # checked in or moved a moment ago
            _no_show(appointment, actor=None, by="job")
            marked += 1
    return marked
