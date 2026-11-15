"""Appointments for the demo hospitals (HIMS-OPD-002). All people are invented.

Per branch, booked by its front desk into the doctors' sessions of the next two weeks:

* up to five patients in the cardiologist's first session with enough free slots (new and
  follow-up visits), and one more over the slots (the consultants allow two extra bookings);
* one of them moved to a later slot ("the patient asked for later"), another cancelled at the
  patient's request;
* a patient of the obstetrician, who is then called away for that day: the patient is listed
  under "To move" on the Appointments page, with why.

Used by the seed and, for a hospital filled before HIMS-OPD-002 (the hosted Development
hospital), by ``add_demo_appointments``. Everything goes through the services, so every rule is
checked and every change is in the audit log.
"""

from datetime import timedelta

from apps.access_control.models import RoleAssignment
from apps.facilities.models import Department, Facility
from apps.organizations.dates import hospital_today
from apps.patients.models import Patient
from apps.scheduling import availability
from apps.scheduling.booking import book, cancel, reschedule
from apps.scheduling.models import Appointment, ScheduleException
from apps.scheduling.services import add_exception

from .opd import _doctors

REASONS = ("Chest pain on walking", "Blood pressure review", "Palpitations", "ECG report", "")
LOOK_AHEAD_DAYS = 14


def front_desks() -> dict:
    """Each branch's front desk account (facility id -> user), for a hospital filled earlier."""
    found = {}
    for assignment in RoleAssignment.objects.filter(
        role__code="receptionist", facility__isnull=False, revoked_at__isnull=True
    ).select_related("user"):
        found.setdefault(assignment.facility_id, assignment.user)
    return found


def _patients(facility: Facility) -> list[Patient]:
    return list(
        Patient.objects.filter(
            registered_facility=facility,
            status=Patient.Status.ACTIVE,
            is_restricted=False,
            is_unknown=False,
        ).order_by("created_at")[:12]
    )


def _free(staff, department, today, *, wanted: int):
    """The doctor's first session in the next two weeks with ``wanted`` free slots."""
    plan = availability.plan_for(
        staff_ids=[staff.pk],
        first=today + timedelta(days=1),
        last=today + timedelta(days=LOOK_AHEAD_DAYS),
        department=department,
        details=True,
    )
    for n in range(1, LOOK_AHEAD_DAYS + 1):
        for session in plan.on(staff.pk, today + timedelta(days=n)):
            free = [s for s in session.slots() if not session.is_taken(*s)]
            if len(free) >= wanted:
                return session, free
    return None, []


def add_appointment_examples(*, actor, desks: dict | None = None) -> list[str]:
    """Book, move and cancel the examples in every branch; returns lines saying what to look at."""
    desks = desks or {}
    notes = []
    for facility in Facility.objects.order_by("created_at"):
        today = hospital_today(facility)
        desk = desks.get(facility.pk) or actor
        people = _patients(facility)
        if len(people) < 5:
            continue
        # The obstetrics patient is the last; one goes over the slots; the rest (three to five)
        # are booked in cardiology, the last two of them then moved and cancelled.
        ward_patient, extra_patient, booked = (
            people[-1],
            people[-2],
            people[: min(5, len(people) - 2)],
        )
        departments = {
            d.code: d
            for d in Department.objects.filter(
                facility=facility, code__in=("CARD", "OBGY"), status=Department.Status.ACTIVE
            ).select_related("facility")
        }
        card = departments.get("CARD")
        doctors = _doctors(card) if card else []
        wanted = len(booked) + 1  # and one free slot to move to
        session, free = _free(doctors[0], card, today, wanted=wanted) if doctors else (None, [])
        if session is not None:
            made = [
                book(
                    actor=desk,
                    patient=patient,
                    staff=doctors[0],
                    department=card,
                    starts_at=free[k][0],
                    kind=Appointment.Kind.FOLLOW_UP if k % 2 else Appointment.Kind.NEW,
                    reason=REASONS[k],
                )
                for k, patient in enumerate(booked)
            ]
            if session.extra_bookings_allowed:
                book(
                    actor=desk,
                    patient=extra_patient,
                    staff=doctors[0],
                    department=card,
                    starts_at=free[0][0],
                    extra=True,
                    reason="Reports to show",
                )
            reschedule(
                actor=desk,
                appointment_id=made[-2].pk,
                version=made[-2].version,
                starts_at=free[len(booked)][0],
                note="The patient asked for later",
            )
            cancel(
                actor=desk,
                appointment_id=made[-1].pk,
                version=made[-1].version,
                reason=Appointment.CancelReason.PATIENT_REQUEST,
                note="Feeling better",
            )
            notes.append(
                f"{facility.name}: Cardiology, {session.day:%a %d %b}: {len(made) - 1} booked (one "
                "moved later), one over the slots, one cancelled"
            )
        obgy = departments.get("OBGY")
        doctors = _doctors(obgy) if obgy else []
        session, free = _free(doctors[0], obgy, today, wanted=1) if doctors else (None, [])
        if session is not None:
            book(
                actor=desk,
                patient=ward_patient,
                staff=doctors[0],
                department=obgy,
                starts_at=free[0][0],
                reason="Antenatal check",
            )
            add_exception(
                actor=actor,
                kind=ScheduleException.Kind.LEAVE,
                facility=facility,
                staff=doctors[0],
                department=obgy,
                start_date=session.day,
                reason="Called to the labour ward",
            )
            notes.append(
                f"{facility.name}: Obstetrics, {session.day:%a %d %b}: the doctor is called away; "
                "one booked patient is listed under To move"
            )
    return notes
