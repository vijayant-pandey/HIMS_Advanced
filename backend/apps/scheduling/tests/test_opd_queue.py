"""The day of the visit: check-in with token numbers, walk-ins, the OPD queue and the patients who
did not come (HIMS-OPD-003; spec 4.6; P0 part 01 section 4, part 03 "Appointment", D10, D12).
All people are invented.

Booked appointments for today are made with the clock set to just after midnight, so their
slots are still to come at any hour the tests run; the rest of the day's rules are checked with
the clock set where each test says.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.features.models import FeatureFlag
from apps.organizations.dates import hospital_today
from apps.patients import restricted
from apps.patients.models import Patient
from apps.scheduling import booking, opd_queue, selectors, services
from apps.scheduling.models import Appointment
from common.admin.tests.test_console_additions import console
from common.exceptions import ConflictError

from .conftest import API
from .test_appointments import at, day_view, slot


def _today(department):
    return hospital_today(department.facility)


def clock(department, hour, minute=0):
    """Set the clock to this time today on the facility's clock."""
    moment = at(department, _today(department), hour, minute)
    return patch("django.utils.timezone.now", return_value=moment)


def book_today(staff, department, person, hour, minute=0):
    """Booked earlier today (just after midnight) into today's slot at this time."""
    with clock(department, 0, 1):
        return booking.book(
            actor=None,
            patient=person,
            staff=staff,
            department=department,
            starts_at=at(department, _today(department), hour, minute),
        )


def step(client, appointment, name, **body):
    appointment.refresh_from_db()
    return client.post(
        f"{API}/appointments/{appointment.pk}/{name}/", {"version": appointment.version, **body}
    )


def walk_in(client, person, staff, department, **body):
    return client.post(
        f"{API}/appointments/walk-in/",
        {
            "patient": str(person.pk),
            "staff": str(staff.pk),
            "department": str(department.pk),
            **body,
        },
    )


def queue(client, department):
    return client.get(f"{API}/appointments/queue/", {"department": department.pk}).json()


# --- Check-in ----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_patients_get_the_doctors_tokens_in_the_order_they_arrive(
    client_for, desk, patient, ravi, department_a, sessions
):
    client = client_for(desk)
    asha, bina = patient("Asha"), patient("Bina")
    first = book_today(ravi, department_a, asha, 9)
    second = book_today(ravi, department_a, bina, 9, 10)
    answer = step(client, second, "check-in")  # Bina comes first
    assert answer.status_code == 200, answer.content
    assert (answer.json()["status"], answer.json()["token_number"]) == ("checked_in", 1)
    assert step(client, first, "check-in").json()["token_number"] == 2
    again = step(client, first, "check-in")
    assert again.status_code == 409 and again.json()["code"] == "ALREADY_CHECKED_IN"
    event = AuditEvent.objects.filter(action=AuditAction.APPOINTMENT_CHECKED_IN).first()
    assert event.metadata["token"] in (1, 2)
    # Checked in, they keep their slots.
    view = day_view(client, department_a, _today(department_a))
    _, found = slot(view, ravi, at(department_a, _today(department_a), 9))
    assert found["is_booked"]
    shown = queue(client, department_a)
    assert shown["is_today"] and shown["can_manage"]
    assert [(a["patient_name"], a["token_number"]) for a in shown["appointments"]] == [
        (bina.full_name, 1),
        (asha.full_name, 2),
    ]


@pytest.mark.django_db
def test_check_in_is_on_the_appointments_day_only(
    client_for, desk, patient, ravi, department_a, sessions
):
    client = client_for(desk)
    later = booking.book(
        actor=None,
        patient=patient("Asha"),
        staff=ravi,
        department=department_a,
        starts_at=at(department_a, _today(department_a) + timedelta(days=2), 9),
    )
    answer = step(client, later, "check-in")
    assert answer.status_code == 409 and answer.json()["code"] == "NOT_TODAY"
    cancelled = book_today(ravi, department_a, patient("Bina"), 10)
    booking.cancel(
        actor=None, appointment_id=cancelled.pk, version=cancelled.version, reason="hospital"
    )
    assert step(client, cancelled, "check-in").json()["code"] == "NOT_BOOKED"


@pytest.mark.django_db
def test_a_doctor_away_now_is_not_checked_in_to(
    client_for, desk, patient, ravi, department_a, sessions
):
    made = book_today(ravi, department_a, patient(), 11)
    services.add_exception(
        actor=None,
        kind="leave",
        facility=department_a.facility,
        staff=ravi,
        department=department_a,
        start_date=_today(department_a),
        reason="Called away",
    )
    answer = step(client_for(desk), made, "check-in")
    assert answer.status_code == 409 and answer.json()["code"] == "SESSION_OFF"
    assert "Called away" not in answer.json()["detail"]  # why is for those keeping schedules


# --- Walk-ins ----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_walk_in_gets_the_next_token_and_takes_no_slot(
    client_for, desk, patient, ravi, mohan, department_a, sessions
):
    client = client_for(desk)
    asha, chitra = patient("Asha"), patient("Chitra")
    booked = book_today(ravi, department_a, asha, 9)
    step(client, booked, "check-in")
    before = day_view(client, department_a, _today(department_a))
    answer = walk_in(client, chitra, ravi, department_a, reason="Fever since yesterday")
    assert answer.status_code == 201, answer.content
    body = answer.json()
    assert (body["source"], body["status"], body["token_number"]) == ("walk_in", "checked_in", 2)
    assert body["source_label"] == "Walk-in"
    after = day_view(client, department_a, _today(department_a))
    assert [s["free_slots"] for d in after["doctors"] for s in d["sessions"]] == [
        s["free_slots"] for d in before["doctors"] for s in d["sessions"]
    ]
    assert AuditEvent.objects.filter(action=AuditAction.APPOINTMENT_WALK_IN).count() == 1
    # Already waiting; booked today with this doctor; nobody in the doctor's session.
    again = walk_in(client, chitra, mohan, department_a)
    assert again.json()["code"] == "ALREADY_WAITING"
    bina = patient("Bina")
    book_today(mohan, department_a, bina, 12)
    assert walk_in(client, bina, mohan, department_a).json()["code"] == "HAS_APPOINTMENT"


@pytest.mark.django_db
def test_a_walk_in_needs_the_doctors_session_today(client_for, desk, patient, ravi, department_a):
    answer = walk_in(client_for(desk), patient(), ravi, department_a)
    assert answer.status_code == 409 and answer.json()["code"] == "NO_SESSION_TODAY"


# --- The queue ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_call_next_takes_the_lowest_token_and_the_doctor_finishes_with_seen(
    client_for, desk, patient, ravi, department_a, sessions
):
    client = client_for(desk)
    for name in ("Asha", "Bina", "Chitra"):
        walk_in(client, patient(name), ravi, department_a)
    call = {"department": str(department_a.pk), "staff": str(ravi.pk)}
    first = client.post(f"{API}/appointments/call-next/", call).json()
    assert (first["called"]["token_number"], first["seen"]) == (1, [])
    assert first["called"]["status"] == "in_consultation" and first["called"]["called_at"]
    second = client.post(f"{API}/appointments/call-next/", call).json()
    assert second["called"]["token_number"] == 2
    assert [(a["token_number"], a["status"]) for a in second["seen"]] == [(1, "completed")]
    with_doctor = Appointment.objects.get(token_number=2, staff=ravi)
    assert step(client, with_doctor, "seen").json()["status"] == "completed"
    third = Appointment.objects.get(token_number=3, staff=ravi)
    left = step(client, third, "left", note="Could not wait")
    assert (left.json()["status"], left.json()["cancel_reason"]) == ("cancelled", "left_unseen")
    assert left.json()["token_number"] == 3  # kept on record with the token
    nobody = client.post(f"{API}/appointments/call-next/", call)
    assert nobody.status_code == 409 and nobody.json()["code"] == "NONE_WAITING"
    assert step(client, third, "seen").json()["code"] == "NOT_WITH_DOCTOR"
    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {AuditAction.APPOINTMENT_CALLED, AuditAction.APPOINTMENT_SEEN} <= actions
    assert AuditAction.APPOINTMENT_LEFT in actions


# --- Did not come ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_job_marks_patients_who_did_not_come_once_the_session_ends(
    client_for, desk, patient, ravi, department_a, sessions
):
    asha, bina, chitra = patient("Asha"), patient("Bina"), patient("Chitra")
    early = book_today(ravi, department_a, asha, 9)
    late = book_today(ravi, department_a, bina, 11)
    came = book_today(ravi, department_a, chitra, 12)
    step(client_for(desk), came, "check-in")
    today = _today(department_a)
    # During the session nothing is marked; the front desk may mark a passed time only.
    assert opd_queue.mark_no_shows(now=at(department_a, today, 10)) == 0
    with clock(department_a, 10):
        with pytest.raises(ConflictError) as refused:
            opd_queue.mark_no_show(actor=desk, appointment_id=late.pk, version=late.version)
        assert refused.value.code == "NOT_YET"
        marked = opd_queue.mark_no_show(actor=desk, appointment_id=early.pk, version=early.version)
        assert marked.status == "no_show"
        undone = opd_queue.undo_no_show(actor=desk, appointment_id=early.pk, version=marked.version)
        assert undone.status == "booked"
    # At 13:30 the session (09:00-13:00) is over: both booked patients are marked, once.
    assert opd_queue.mark_no_shows(now=at(department_a, today, 13, 30)) == 2
    assert opd_queue.mark_no_shows(now=at(department_a, today, 13, 45)) == 0
    statuses = dict(Appointment.objects.values_list("patient_id", "status"))
    assert (statuses[asha.pk], statuses[bina.pk], statuses[chitra.pk]) == (
        "no_show",
        "no_show",
        "checked_in",
    )
    assert selectors.to_rebook(department_a, details=False) == []
    # Too late to undo; the patient came late after all: checked in with a token.
    late.refresh_from_db()
    with clock(department_a, 13, 30):
        with pytest.raises(ConflictError) as refused:
            opd_queue.undo_no_show(actor=desk, appointment_id=late.pk, version=late.version)
        assert refused.value.code == "SESSION_OVER"
        checked = opd_queue.check_in(actor=desk, appointment_id=late.pk, version=late.version)
    assert (checked.status, checked.token_number) == ("checked_in", 2)
    event = AuditEvent.objects.get(
        action=AuditAction.APPOINTMENT_CHECKED_IN, resource_id=str(late.pk)
    )
    assert event.metadata["late"] is True
    by_job = AuditEvent.objects.filter(action=AuditAction.APPOINTMENT_NO_SHOW)
    assert sorted(e.metadata["by"] for e in by_job) == ["front_desk", "job", "job"]


# --- Who may, restricted records, the feature ----------------------------------------------------


@pytest.mark.django_db
def test_the_head_of_department_sees_the_queue_but_does_not_move_it(
    client_for, hod, desk, patient, ravi, department_a, sessions
):
    walk_in(client_for(desk), patient(), ravi, department_a)
    client = client_for(hod)
    shown = queue(client, department_a)
    assert not shown["can_manage"] and len(shown["appointments"]) == 1
    call = {"department": str(department_a.pk), "staff": str(ravi.pk)}
    assert client.post(f"{API}/appointments/call-next/", call).status_code == 403


@pytest.mark.django_db
def test_a_restricted_record_is_checked_in_only_by_those_who_may_open_it(
    client_for, make_user, system_roles, desk, patient, ravi, department_a, sessions
):
    officer = make_user(role=system_roles["medical-records-officer"])
    vip = patient("Kavya", "Rao")
    vip = restricted.set_restriction(
        actor=officer,
        patient_id=vip.pk,
        version=vip.version,
        restricted=True,
        restriction=Patient.Restriction.VIP,
        reason="Well-known public figure",
    )
    made = book_today(ravi, department_a, vip, 9)
    client = client_for(desk)
    assert step(client, made, "check-in").json()["code"] == "RESTRICTED_RECORD"
    assert walk_in(client, vip, ravi, department_a).json()["code"] == "RESTRICTED_RECORD"
    opd_queue.check_in(actor=officer, appointment_id=made.pk, version=made.version)
    shown = queue(client, department_a)["appointments"]
    assert [(a["patient_name"], a["token_number"]) for a in shown] == [("Restricted record", 1)]
    # Moving the queue shows nothing more, so the front desk may call the patient in.
    call = {"department": str(department_a.pk), "staff": str(ravi.pk)}
    called = client.post(f"{API}/appointments/call-next/", call).json()["called"]
    assert called["patient_name"] == "Restricted record"


@pytest.mark.django_db
def test_outpatient_switched_off_stops_the_queue(
    client_for, desk, patient, ravi, department_a, sessions
):
    FeatureFlag.objects.create(
        organization_id=department_a.organization_id,
        facility=department_a.facility,
        key="outpatient.appointments",
        enabled=False,
    )
    answer = walk_in(client_for(desk), patient(), ravi, department_a)
    assert answer.status_code == 409 and answer.json()["code"] == "FEATURE_DISABLED"


# --- Admin console ------------------------------------------------------------------------------

CONSOLE = "/admin/scheduling/appointment/"


@pytest.mark.django_db
def test_console_checks_in_walks_in_and_calls_the_next_patient(
    admin_user, desk, patient, ravi, department_a, sessions
):
    client, asha, bina = console(admin_user), patient("Asha"), patient("Bina")
    made = book_today(ravi, department_a, asha, 9)
    client.post(CONSOLE, {"action": "check_in", "_selected_action": [str(made.pk)]})
    made.refresh_from_db()
    assert (made.status, made.token_number) == ("checked_in", 1)
    page = f"{CONSOLE}queue/?department={department_a.pk}"
    shown = client.get(page).content.decode()
    assert "OPD queue (today)" in shown and asha.mrn in shown
    added = client.post(page, {"walk_in": "1", "mrn": bina.mrn, "staff": ravi.pk, "kind": "new"})
    assert added.status_code == 200
    walked = Appointment.objects.get(patient=bina)
    assert (walked.source, walked.token_number) == ("walk_in", 2)
    client.post(page, {"call_next": str(ravi.pk)})
    made.refresh_from_db()
    assert made.status == "in_consultation"
    client.post(CONSOLE, {"action": "mark_seen", "_selected_action": [str(made.pk)]})
    made.refresh_from_db()
    assert made.status == "completed"
    listed = client.get(CONSOLE).content.decode()
    assert "OPD queue" in listed and "Walk-in" in listed
