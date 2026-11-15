"""Appointments: booking into doctors' OPD slots, moving and cancelling (HIMS-OPD-002; spec 4.6;
P0 part 01 section 4 and part 06). All people are invented."""

import threading
from datetime import datetime, time, timedelta

import pytest
from django.db import connection

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.features.models import FeatureFlag
from apps.numbering.services import ensure_default_schemes
from apps.organizations.dates import hospital_timezone, hospital_today
from apps.patients import restricted
from apps.patients.models import Patient
from apps.patients.services import register_patient
from apps.rosters.services import approve_leave, request_leave
from apps.scheduling import booking, services
from apps.scheduling.models import Appointment
from common.admin.tests.test_console_additions import console
from common.exceptions import ConflictError

from .conftest import API

ALL_DAYS = range(7)


@pytest.fixture
def ravi(doctor, department_a):
    return doctor(department_a, given="Ravi")


@pytest.fixture
def mohan(doctor, department_a):
    return doctor(department_a, given="Mohan")


@pytest.fixture
def day():
    return hospital_today() + timedelta(days=2)


@pytest.fixture
def sessions(ravi, mohan, department_a):
    """Every day 09:00-13:00 for both doctors, 10-minute slots; Ravi allows one extra booking."""
    for staff, extra in ((ravi, 1), (mohan, 0)):
        services.add_sessions(
            actor=None,
            staff=staff,
            department=department_a,
            weekdays=ALL_DAYS,
            start_time=time(9),
            end_time=time(13),
            valid_from=hospital_today(),
            extra_bookings_allowed=extra,
        )


@pytest.fixture
def desk(make_user, system_roles, facility_a, organization):
    ensure_default_schemes(organization)
    return make_user(
        role=system_roles["receptionist"], facility=facility_a, display_name="Synthetic Desk"
    )


@pytest.fixture
def patient(desk, facility_a):
    def factory(given="Asha", family="Kumar"):
        return register_patient(
            actor=desk,
            facility=facility_a,
            data={
                "given_name": given,
                "family_name": family,
                "sex": "female",
                "age_years": 40,
                "has_no_phone": True,
            },
            privacy_notice="given",
        )

    return factory


def at(department, day, hour, minute=0):
    return datetime.combine(day, time(hour, minute), tzinfo=hospital_timezone(department.facility))


def book(client, patient, staff, department, starts_at, **extra):
    return client.post(
        f"{API}/appointments/",
        {
            "patient": str(patient.pk),
            "staff": str(staff.pk),
            "department": str(department.pk),
            "starts_at": starts_at.isoformat(),
            **extra,
        },
    )


def day_view(client, department, day):
    return client.get(
        f"{API}/appointments/day/", {"department": department.pk, "date": day.isoformat()}
    ).json()


def slot(data, staff, starts_at):
    doctor = next(d for d in data["doctors"] if d["staff_id"] == str(staff.pk))
    for session in doctor["sessions"]:
        for found in session["slots"]:
            if found["time"] == f"{starts_at:%H:%M}":
                return session, found
    raise AssertionError("no such slot")


# --- Booking -----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_front_desk_books_a_free_slot_and_it_shows_as_booked(
    client_for, desk, patient, ravi, department_a, sessions, day
):
    asha = patient()
    client = client_for(desk)
    answer = book(
        client, asha, ravi, department_a, at(department_a, day, 9, 10), reason="Chest pain"
    )
    assert answer.status_code == 201, answer.content
    body = answer.json()
    assert (body["time"], body["status"], body["kind"]) == ("09:10", "booked", "new")
    assert body["patient_name"] == asha.full_name and body["patient_mrn"] == asha.mrn
    session, found = slot(day_view(client, department_a, day), ravi, at(department_a, day, 9, 10))
    assert found["is_booked"] and (session["booked"], session["free_slots"]) == (1, 23)
    event = AuditEvent.objects.get(action=AuditAction.APPOINTMENT_BOOKED)
    assert event.resource_id == body["id"] and "Chest pain" not in str(event.changes)
    # The doctor's own week counts the booked patient.
    week = client_for(ravi.user).get(f"{API}/my-opd-sessions/", {"start": day.isoformat()})
    assert week.json()["days"][0]["sessions"][0]["booked"] == 1


@pytest.mark.django_db
def test_a_taken_slot_is_refused_and_extra_bookings_follow_the_session(
    client_for, desk, patient, ravi, mohan, department_a, sessions, day
):
    client = client_for(desk)
    first, second, third = patient("Asha"), patient("Bina"), patient("Chitra")
    nine = at(department_a, day, 9)
    assert book(client, first, ravi, department_a, nine).status_code == 201
    taken = book(client, second, ravi, department_a, nine)
    assert taken.status_code == 409 and taken.json()["code"] == "SLOT_TAKEN"
    assert "1 left" in taken.json()["detail"]  # Ravi allows one booking over the slots
    free = book(client, second, ravi, department_a, at(department_a, day, 9, 20), extra=True)
    assert free.json()["code"] == "EXTRA_NOT_NEEDED"
    over = book(client, second, ravi, department_a, nine, extra=True)
    assert over.status_code == 201 and over.json()["is_extra"] is True
    full = book(client, third, ravi, department_a, nine, extra=True)
    assert full.json()["code"] == "EXTRA_FULL"
    # Mohan allows none.
    assert book(client, third, mohan, department_a, nine).status_code == 201
    none = book(client, first, mohan, department_a, nine, extra=True)
    assert none.json()["code"] in ("EXTRA_FULL", "PATIENT_ALREADY_BOOKED")


@pytest.mark.django_db
def test_only_free_slots_inside_a_session_can_be_booked(
    client_for, desk, patient, ravi, department_a, sessions, day
):
    client, asha = client_for(desk), patient()
    for when, code in (
        (at(department_a, day, 14), "NOT_A_FREE_SLOT"),  # after the session
        (at(department_a, day, 9, 5), "NOT_A_FREE_SLOT"),  # not a slot's start
        (at(department_a, hospital_today() - timedelta(days=1), 9), "SLOT_IN_PAST"),
        (at(department_a, hospital_today() + timedelta(days=181), 9), "TOO_FAR"),
    ):
        answer = book(client, asha, ravi, department_a, when)
        assert (answer.status_code, answer.json()["code"]) == (409, code), when
    # The doctor away for the morning: those slots cannot be booked.
    services.add_exception(
        actor=None,
        kind="leave",
        facility=department_a.facility,
        staff=ravi,
        department=department_a,
        start_date=day,
        start_time=time(9),
        end_time=time(11),
        reason="Committee",
    )
    away = book(client, asha, ravi, department_a, at(department_a, day, 9, 30))
    assert away.json()["code"] == "NOT_A_FREE_SLOT"
    assert book(client, asha, ravi, department_a, at(department_a, day, 11)).status_code == 201


@pytest.mark.django_db
def test_one_patient_is_not_booked_twice_at_once_nor_a_merged_record(
    client_for, desk, patient, ravi, mohan, department_a, sessions, day
):
    client, asha = client_for(desk), patient()
    nine = at(department_a, day, 9)
    assert book(client, asha, ravi, department_a, nine).status_code == 201
    twice = book(client, asha, mohan, department_a, nine)
    assert twice.json()["code"] == "PATIENT_ALREADY_BOOKED"
    Patient.objects.filter(pk=asha.pk).update(
        status=Patient.Status.MERGED, merged_into=patient("Other").pk
    )
    merged = book(client, asha, mohan, department_a, at(department_a, day, 10))
    assert merged.json()["code"] == "PATIENT_MERGED"


@pytest.mark.django_db(transaction=True)
def test_two_receptionists_booking_one_slot_at_the_same_moment_one_wins(
    desk, patient, ravi, department_a, sessions, day
):
    """Past every check in the service (each request takes the doctor's lock in turn), the
    database's exclusion constraint is what makes this safe; both are exercised here."""
    first, second = patient("Asha"), patient("Bina")
    nine = at(department_a, day, 9)
    results, start = [], threading.Barrier(2)

    def worker(person):
        try:
            start.wait()
            booking.book(
                actor=desk, patient=person, staff=ravi, department=department_a, starts_at=nine
            )
            results.append("booked")
        except ConflictError as exc:
            results.append(exc.code)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(p,)) for p in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["SLOT_TAKEN", "booked"]
    assert Appointment.objects.filter(starts_at=nine).count() == 1


# --- Moving and cancelling ----------------------------------------------------------------------


@pytest.mark.django_db
def test_moving_keeps_both_linked_and_frees_the_old_slot(
    client_for, desk, patient, ravi, mohan, department_a, sessions, day
):
    client, asha = client_for(desk), patient()
    old = book(client, asha, ravi, department_a, at(department_a, day, 9)).json()
    stale = client.post(
        f"{API}/appointments/{old['id']}/reschedule/",
        {"version": 99, "starts_at": at(department_a, day, 10).isoformat()},
    )
    assert stale.status_code == 409
    moved = client.post(
        f"{API}/appointments/{old['id']}/reschedule/",
        {
            "version": old["version"],
            "starts_at": at(department_a, day, 10).isoformat(),
            "staff": str(mohan.pk),
            "note": "Patient asked for later",
        },
    )
    assert moved.status_code == 200, moved.content
    new = moved.json()
    assert (new["staff_id"], new["time"], new["rescheduled_from_id"]) == (
        str(mohan.pk),
        "10:00",
        old["id"],
    )
    before = client.get(f"{API}/appointments/{old['id']}/").json()
    assert (before["status"], before["cancel_reason"]) == ("cancelled", "rescheduled")
    assert before["rescheduled_to_id"] == new["id"]
    assert AuditEvent.objects.filter(action=AuditAction.APPOINTMENT_RESCHEDULED).count() == 1
    # The old slot is free again.
    assert (
        book(client, patient("Bina"), ravi, department_a, at(department_a, day, 9)).status_code
        == 201
    )


@pytest.mark.django_db
def test_cancelling_needs_a_reason_and_frees_the_slot(
    client_for, desk, patient, ravi, department_a, sessions, day
):
    client, asha = client_for(desk), patient()
    made = book(client, asha, ravi, department_a, at(department_a, day, 9)).json()
    url = f"{API}/appointments/{made['id']}/cancel/"
    assert client.post(url, {"version": made["version"]}).status_code == 400
    moved_reason = client.post(url, {"version": made["version"], "reason": "rescheduled"})
    assert moved_reason.status_code == 400  # "moved" is recorded by moving, not chosen
    done = client.post(url, {"version": made["version"], "reason": "patient_request"})
    assert done.status_code == 200 and done.json()["status"] == "cancelled"
    again = client.post(url, {"version": done.json()["version"], "reason": "hospital"})
    assert again.json()["code"] == "NOT_BOOKED"
    assert (
        book(client, patient("Bina"), ravi, department_a, at(department_a, day, 9)).status_code
        == 201
    )
    listed = client.get(f"{API}/appointments/", {"patient_id": asha.pk}).json()
    assert [a["status"] for a in listed] == ["cancelled"]
    assert (
        client.get(f"{API}/appointments/", {"patient_id": asha.pk, "upcoming": "true"}).json() == []
    )


# --- When the doctor cannot come ----------------------------------------------------------------


@pytest.mark.django_db
def test_doctor_away_lists_the_patients_to_move(
    client_for, hod, desk, patient, ravi, department_a, sessions, day
):
    desk_client = client_for(desk)
    asha = patient()
    book(desk_client, asha, ravi, department_a, at(department_a, day, 9, 30))
    answer = client_for(hod).post(
        f"{API}/schedule-exceptions/",
        {
            "kind": "leave",
            "staff": str(ravi.pk),
            "department": str(department_a.pk),
            "start_date": day.isoformat(),
            "reason": "Conference",
        },
    )
    assert answer.status_code == 201
    assert [b["patient_mrn"] for b in answer.json()["bookings"]] == [asha.mrn]
    rebook = desk_client.get(f"{API}/appointments/to-rebook/", {"department": department_a.pk})
    (row,) = rebook.json()
    assert row["appointment"]["patient_mrn"] == asha.mrn and row["why"] == "Away"
    # The head of department, who keeps the schedules, sees why.
    hod_rows = client_for(hod).get(
        f"{API}/appointments/to-rebook/", {"department": department_a.pk}
    )
    assert hod_rows.json()[0]["why"] == "Away: Conference"


@pytest.mark.django_db
def test_leave_on_the_leave_page_shows_the_bookings_and_then_lists_them(
    client_for, hod, desk, patient, ravi, department_a, sessions, day
):
    book(client_for(desk), patient(), ravi, department_a, at(department_a, day, 9))
    leave = request_leave(
        actor=ravi.user,
        staff=ravi,
        department=department_a,
        leave_type="casual",
        start_date=day,
        end_date=day,
    )
    shown = client_for(hod).get(f"{API}/leave-requests/{leave.pk}/").json()
    assert shown["opd_bookings"] == 1
    approve_leave(actor=hod, leave_id=leave.pk, version=leave.version)
    rows = client_for(desk).get(f"{API}/appointments/to-rebook/", {"department": department_a.pk})
    assert rows.json()[0]["why"] == "On leave (approved on the Leave page)"


@pytest.mark.django_db
def test_slot_length_cannot_change_under_booked_patients(
    client_for, hod, desk, patient, ravi, department_a, sessions, day
):
    book(client_for(desk), patient(), ravi, department_a, at(department_a, day, 9))
    schedule = Appointment.objects.get().schedule
    changed = client_for(hod).patch(
        f"{API}/doctor-schedules/{schedule.pk}/",
        {"version": schedule.version, "slot_minutes": 15},
    )
    assert changed.json()["code"] == "SESSION_HAS_BOOKINGS"
    note = client_for(hod).patch(
        f"{API}/doctor-schedules/{schedule.pk}/", {"version": schedule.version, "note": "Room 2"}
    )
    assert note.status_code == 200


# --- Who may do what ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_who_may_book(
    client_for,
    make_user,
    system_roles,
    hod,
    patient,
    ravi,
    department_a,
    department_b,
    sessions,
    day,
):
    asha = patient()
    nine = at(department_a, day, 9)
    # The head of department sees appointments but does not book (P0 part 04).
    assert (
        client_for(hod).get(f"{API}/appointments/day/", {"department": department_a.pk}).status_code
        == 200
    )
    assert book(client_for(hod), asha, ravi, department_a, nine).status_code == 403
    # An OPD scheduler for another department cannot book here.
    other = make_user(
        role=system_roles["scheduler"], facility=department_b.facility, department=department_b
    )
    assert book(client_for(other), asha, ravi, department_a, nine).status_code == 403
    mine = make_user(
        role=system_roles["scheduler"], facility=department_a.facility, department=department_a
    )
    assert book(client_for(mine), asha, ravi, department_a, nine).status_code == 201
    # A list needs a patient, a department or a doctor.
    assert client_for(mine).get(f"{API}/appointments/").status_code == 400


@pytest.mark.django_db
def test_a_restricted_record_is_booked_only_by_those_who_may_open_it(
    client_for, make_user, system_roles, desk, patient, ravi, department_a, sessions, day
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
    refused = book(client_for(desk), vip, ravi, department_a, at(department_a, day, 9))
    assert refused.json()["code"] == "RESTRICTED_RECORD"
    made = booking.book(
        actor=officer,
        patient=vip,
        staff=ravi,
        department=department_a,
        starts_at=at(department_a, day, 9),
        reason="Review",
    )
    shown = day_view(client_for(desk), department_a, day)["appointments"]
    assert [(a["patient_name"], a["reason"], a["patient_mrn"]) for a in shown] == [
        ("Restricted record", "", vip.mrn)
    ]
    assert made.patient_id == vip.pk


@pytest.mark.django_db
def test_outpatient_switched_off_stops_booking(
    client_for, desk, patient, ravi, department_a, sessions, day
):
    FeatureFlag.objects.create(
        organization_id=department_a.organization_id,
        facility=department_a.facility,
        key="outpatient.appointments",
        enabled=False,
    )
    answer = book(client_for(desk), patient(), ravi, department_a, at(department_a, day, 9))
    assert answer.status_code == 409 and answer.json()["code"] == "FEATURE_DISABLED"


# --- Admin console ------------------------------------------------------------------------------

CONSOLE = "/admin/scheduling/appointment/"


@pytest.mark.django_db
def test_console_books_moves_cancels_and_lists_the_patients_to_move(
    admin_user, desk, patient, ravi, department_a, sessions, day
):
    client, asha = console(admin_user), patient()
    added = client.post(
        f"{CONSOLE}add/",
        {
            "patient": asha.pk,
            "staff": ravi.pk,
            "department": department_a.pk,
            "day": day.isoformat(),
            "time": "09:05",
            "kind": "new",
            "source": "phone",
            "reason": "",
        },
    )
    assert "not a free slot" in added.content.decode()  # rules on the form, not a server error
    added = client.post(
        f"{CONSOLE}add/",
        {
            "patient": asha.pk,
            "staff": ravi.pk,
            "department": department_a.pk,
            "day": day.isoformat(),
            "time": "09:00",
            "kind": "new",
            "source": "phone",
            "reason": "Follow-up of tests",
        },
    )
    assert added.status_code == 302, added.content.decode()[:2000]
    made = Appointment.objects.get()
    assert made.source == "phone"
    assert AuditEvent.objects.filter(action=AuditAction.APPOINTMENT_BOOKED).exists()
    move = f"{CONSOLE}{made.pk}/move/"
    assert "Move an appointment" in client.get(move).content.decode()
    moved = client.post(move, {"day": day.isoformat(), "time": "10:00"})
    assert moved.status_code == 302
    new = Appointment.objects.get(rescheduled_from=made)
    assert f"{new.starts_at.astimezone(hospital_timezone(department_a.facility)):%H:%M}" == "10:00"
    services.add_exception(
        actor=None,
        kind="leave",
        facility=department_a.facility,
        staff=ravi,
        department=department_a,
        start_date=day,
        reason="Conference",
    )
    page = client.get(f"{CONSOLE}to-move/", {"department": department_a.pk}).content.decode()
    assert asha.mrn in page and "Away: Conference" in page
    client.post(CONSOLE, {"action": "cancel_doctor_unavailable", "_selected_action": [str(new.pk)]})
    new.refresh_from_db()
    assert (new.status, new.cancel_reason) == ("cancelled", "doctor_unavailable")
    assert asha.mrn in client.get(CONSOLE).content.decode()
    chart = client.get(f"/admin/patients/patient/{asha.pk}/change/").content.decode()
    assert "Upcoming appointments" in chart
