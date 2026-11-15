"""Today's OPD queue for the demo hospitals (HIMS-OPD-003). All people are invented.

Per branch, with a doctor who has an OPD session today (when none has, the general physician gets
an extra session today, 08:00-20:00, "Demo OPD queue"):

* four patients booked into the session's first slots (as if booked this morning);
* three of them checked in (tokens 1-3, in the order they came, not their slot times) and a walk-in
  (token 4, no slot);
* **Call next** twice: token 1 seen, token 2 with the doctor; tokens 3 and 4 waiting;
* the fourth still to come, or marked "did not come" when its time has passed (by the front desk;
  the no-show job marks the patients of sessions that ended).

Today moves on, so ``add_demo_opd_queue`` adds a new day's queue to a hospital filled earlier
(the hosted Development hospital), once a day. Check-in, walk-ins, the queue and the no-shows go
through the services (every rule checked, every change audited). The morning's bookings are
written as they would have been then: their slots may already have passed when this runs.
"""

from datetime import time

from django.db.models import Q
from django.utils import timezone

from apps.facilities.models import Department, Facility
from apps.organizations.dates import hospital_today
from apps.scheduling import availability, opd_queue
from apps.scheduling.models import Appointment, ScheduleException
from apps.scheduling.services import add_exception
from common.exceptions import DomainError

from .appointments import _patients
from .opd import OPD_DEPARTMENTS, _doctors

REASONS = ("Fever and cough", "Blood pressure review", "Back pain", "Diabetes follow-up")


def _session_today(facility, actor):
    """A doctor's OPD session today in this branch (adding an extra one when none runs)."""
    today = hospital_today(facility)
    departments = list(
        Department.objects.filter(
            facility=facility, code__in=OPD_DEPARTMENTS, status=Department.Status.ACTIVE
        ).select_related("facility")
    )
    departments.sort(key=lambda d: OPD_DEPARTMENTS.index(d.code))
    for department in departments:
        doctors = _doctors(department)
        plan = availability.plan_for(
            staff_ids=[d.pk for d in doctors],
            first=today,
            last=today,
            department=department,
            details=False,
        )
        for doctor in doctors:
            for session in plan.on(doctor.pk, today):
                if session.status == "open":
                    return doctor, department, session, ""
    for department in departments:
        for doctor in _doctors(department):
            try:
                add_exception(
                    actor=actor,
                    kind=ScheduleException.Kind.EXTRA_SESSION,
                    facility=facility,
                    staff=doctor,
                    department=department,
                    start_date=today,
                    start_time=time(8),
                    end_time=time(20),
                    slot_minutes=15,
                    extra_bookings_allowed=0,
                    reason="Demo OPD queue",
                )
            except DomainError:
                continue  # on leave, or a session already that day: try the next doctor
            plan = availability.plan_for(
                staff_ids=[doctor.pk], first=today, last=today, department=department, details=False
            )
            session = next(s for s in plan.on(doctor.pk, today) if s.source == "extra")
            return doctor, department, session, " (an extra session today)"
    return None, None, None, ""


def _booked_this_morning(desk, patient, doctor, department, session, start, end, k):
    """A booking made earlier today, written as the booking service would have saved it."""
    return Appointment.objects.create(
        organization_id=department.organization_id,
        patient=patient,
        staff=doctor,
        facility_id=department.facility_id,
        department=department,
        schedule_id=session.schedule_id,
        extra_session_id=session.exception_id,
        starts_at=start,
        ends_at=end,
        local_date=session.day,
        kind=Appointment.Kind.FOLLOW_UP if k % 2 else Appointment.Kind.NEW,
        source=Appointment.Source.PHONE if k == 3 else Appointment.Source.FRONT_DESK,
        reason=REASONS[k],
        booked_by=desk,
    )


def add_queue_examples(*, actor, desks: dict | None = None) -> list[str]:
    """Today's queue in every branch; returns lines saying what to look at."""
    desks = desks or {}
    notes = []
    for facility in Facility.objects.order_by("created_at"):
        desk = desks.get(facility.pk) or actor
        today = hospital_today(facility)
        busy = set(
            Appointment.objects.filter(
                Q(status__in=opd_queue.WAITING) | Q(status=Appointment.Status.BOOKED),
                facility=facility,
                local_date=today,
            ).values_list("patient_id", flat=True)
        )
        people = [p for p in _patients(facility) if p.pk not in busy][-5:]
        if len(people) < 5:
            continue
        doctor, department, session, extra = _session_today(facility, actor)
        if session is None:
            continue
        taken = {(b.start, b.end) for b in session.bookings}
        slots = [s for s in session.slots() if s not in taken][:4]
        if len(slots) < 4:
            continue
        booked = [
            _booked_this_morning(desk, people[k], doctor, department, session, *slots[k], k)
            for k in range(4)
        ]
        for appointment in (booked[1], booked[0], booked[2]):  # not in slot order
            opd_queue.check_in(
                actor=desk, appointment_id=appointment.pk, version=appointment.version
            )
        walked = opd_queue.walk_in(
            actor=desk,
            patient=people[4],
            staff=doctor,
            department=department,
            reason="Sudden headache",
        )
        opd_queue.call_next(actor=desk, staff=doctor, department=department)
        opd_queue.call_next(actor=desk, staff=doctor, department=department)
        late = booked[3]
        if late.starts_at < timezone.now():
            opd_queue.mark_no_show(actor=desk, appointment_id=late.pk, version=late.version)
        notes.append(
            f"{facility.name}: OPD queue today, {department.name}, {doctor.given_name} "
            f"{doctor.family_name}{extra}: token 1 seen, token 2 with the doctor, tokens 3 and "
            f"{walked.token_number} (a walk-in) waiting"
        )
    marked = opd_queue.mark_no_shows()
    if marked:
        notes.append(f"The no-show job marked {marked} booked appointment(s) as did not come")
    return notes
