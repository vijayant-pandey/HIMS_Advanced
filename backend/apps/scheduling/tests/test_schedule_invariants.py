"""Artifact A for doctor schedules and appointments: the rules the database itself keeps
(HIMS-OPD-001, HIMS-OPD-002 and HIMS-DATA-004; spec 28.8, "automated tests for critical
invariants").

The services check every rule first and give a plain message. These tests go past the services,
straight to the database, and expect it to refuse. ``RULES`` names every constraint on the
schedule tables; the last test fails when a table gains one that is not listed, so a new rule
cannot be added without its test. All people are invented.
"""

from datetime import datetime, time, timedelta

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models import F
from django.utils import timezone

from apps.numbering.services import ensure_default_schemes
from apps.organizations.dates import hospital_timezone, hospital_today
from apps.patients.services import register_patient
from apps.scheduling.booking import book
from apps.scheduling.models import Appointment, DoctorSchedule, ScheduleException
from apps.scheduling.services import add_exception, add_sessions

TABLES = ["doctor_schedules", "schedule_exceptions", "appointments"]

# Every rule on the schedule tables -> the test that breaks it.
RULES = {
    "doctor_schedule_ends_after_start": "test_a_session_ends_after_it_starts",
    "doctor_schedule_weekday": "test_numbers_stay_in_their_range",
    "doctor_schedules_weekday_check": "test_numbers_stay_in_their_range",
    "doctor_schedule_slot_minutes": "test_numbers_stay_in_their_range",
    "doctor_schedules_slot_minutes_check": "test_numbers_stay_in_their_range",
    "doctor_schedule_extra_bookings": "test_numbers_stay_in_their_range",
    "doctor_schedules_extra_bookings_allowed_check": "test_numbers_stay_in_their_range",
    "doctor_schedule_valid_dates": "test_a_session_ends_after_it_starts",
    "doctor_schedule_no_overlap": "test_two_schedulers_cannot_overlap_one_doctor",
    "doctor_schedules_version_check": "test_numbers_stay_in_their_range",
    "schedule_exception_dates": "test_exception_shapes",
    "schedule_exception_times": "test_exception_shapes",
    "schedule_exception_times_one_day": "test_exception_shapes",
    "schedule_exception_whose": "test_exception_shapes",
    "schedule_exception_extra_session": "test_exception_shapes",
    "schedule_exceptions_slot_minutes_check": "test_exception_shapes",
    "schedule_exceptions_extra_bookings_allowed_check": "test_exception_shapes",
    "schedule_exceptions_version_check": "test_exception_shapes",
    "appointment_ends_after_start": "test_appointment_shapes",
    "appointment_one_session": "test_appointment_shapes",
    "appointment_cancelled": "test_appointment_shapes",
    "appointment_not_moved_to_itself": "test_appointment_shapes",
    "appointments_rescheduled_from_id_key": "test_appointment_shapes",
    "appointments_version_check": "test_appointment_shapes",
    "appointment_no_double_booking": "test_two_receptionists_cannot_double_book_a_doctor",
}


def _refused():
    """The database must refuse what runs inside (in its own savepoint)."""
    return pytest.raises(IntegrityError)


@pytest.fixture
def session(doctor, department_a):
    (created,) = add_sessions(
        actor=None,
        staff=doctor(department_a),
        department=department_a,
        weekdays=[0],
        start_time=time(9),
        end_time=time(13),
        valid_from=hospital_today(),
    )
    return created


@pytest.mark.django_db
def test_a_session_ends_after_it_starts(session):
    rows = DoctorSchedule.objects.filter(pk=session.pk)
    with _refused(), transaction.atomic():
        rows.update(end_time=time(8))
    with _refused(), transaction.atomic():
        rows.update(valid_until=session.valid_from - timedelta(days=1))
    with transaction.atomic():  # the last day may be the first day
        rows.update(valid_until=session.valid_from)


@pytest.mark.django_db
def test_numbers_stay_in_their_range(session):
    rows = DoctorSchedule.objects.filter(pk=session.pk)
    for change in (
        {"weekday": 7},
        {"weekday": -1},
        {"slot_minutes": 4},
        {"slot_minutes": 121},
        {"extra_bookings_allowed": 21},
        {"extra_bookings_allowed": -1},
        {"version": -1},
    ):
        with _refused(), transaction.atomic():
            rows.update(**change)


@pytest.mark.django_db
def test_two_schedulers_cannot_overlap_one_doctor(session):
    """As if two people saved at the same moment, past the service's own check."""
    copy = {
        f.attname: getattr(session, f.attname)
        for f in DoctorSchedule._meta.concrete_fields
        if f.attname not in ("id", "created_at", "updated_at")
    }
    with _refused(), transaction.atomic():
        DoctorSchedule.objects.create(**{**copy, "start_time": time(12), "end_time": time(14)})
    # Other weekdays, later hours, a withdrawn copy or validity after the end are fine.
    with transaction.atomic():
        DoctorSchedule.objects.create(**{**copy, "weekday": 1})
        DoctorSchedule.objects.create(**{**copy, "start_time": time(13), "end_time": time(15)})
        DoctorSchedule.objects.create(**{**copy, "is_active": False})
    DoctorSchedule.objects.filter(pk=session.pk).update(valid_until=session.valid_from)
    with transaction.atomic():
        DoctorSchedule.objects.create(
            **{**copy, "valid_from": session.valid_from + timedelta(days=1), "valid_until": None}
        )


@pytest.mark.django_db
def test_exception_shapes(doctor, department_a):
    staff = doctor(department_a)
    day = hospital_today() + timedelta(days=3)
    leave, _ = add_exception(
        actor=None,
        kind="leave",
        facility=department_a.facility,
        staff=staff,
        department=department_a,
        start_date=day,
        end_date=day + timedelta(days=1),
        reason="Conference",
    )
    extra, _ = add_exception(
        actor=None,
        kind="extra_session",
        facility=department_a.facility,
        staff=staff,
        department=department_a,
        start_date=day + timedelta(days=5),
        start_time=time(14),
        end_time=time(16),
        reason="Health camp",
    )
    leaves = ScheduleException.objects.filter(pk=leave.pk)
    extras = ScheduleException.objects.filter(pk=extra.pk)
    for rows, change in (
        (leaves, {"end_date": day - timedelta(days=1)}),  # ends before it starts
        (leaves, {"start_time": time(10)}),  # a start time without an end time
        (leaves, {"end_date": day, "start_time": time(10), "end_time": time(9)}),
        (leaves, {"start_time": time(9), "end_time": time(10)}),  # times over two days
        (leaves, {"staff": None}),  # leave belongs to a doctor
        (leaves, {"kind": "holiday"}),  # a holiday belongs to no doctor
        (extras, {"start_time": None, "end_time": None}),  # an extra session has hours
        (extras, {"end_date": F("start_date") + timedelta(days=1)}),  # and is one day
        (extras, {"slot_minutes": None}),
        (extras, {"extra_bookings_allowed": None}),
        (extras, {"slot_minutes": 200}),
        (extras, {"extra_bookings_allowed": -1}),
        (extras, {"version": -1}),
    ):
        with _refused(), transaction.atomic():
            rows.update(**change)


@pytest.fixture
def booked(session, organization):
    """Two invented patients, one booked at the session's first slot on its next Monday."""
    ensure_default_schemes(organization)
    department = session.department
    patients = [
        register_patient(
            actor=None,
            facility=department.facility,
            data={
                "given_name": name,
                "family_name": "Invariant",
                "sex": "female",
                "age_years": 30,
                "has_no_phone": True,
            },
        )
        for name in ("Asha", "Bina")
    ]
    day = hospital_today() + timedelta(days=1)
    while day.weekday() != session.weekday:
        day += timedelta(days=1)
    starts_at = datetime.combine(day, time(9), tzinfo=hospital_timezone(department.facility))
    first = book(
        actor=None,
        patient=patients[0],
        staff=session.staff,
        department=department,
        starts_at=starts_at,
    )
    return first, patients[1]


def _copy(appointment, **changes):
    values = {
        f.attname: getattr(appointment, f.attname)
        for f in Appointment._meta.concrete_fields
        if f.attname not in ("id", "created_at", "updated_at")
    }
    return Appointment(**{**values, **changes})


@pytest.mark.django_db
def test_appointment_shapes(booked):
    first, other = booked
    rows = Appointment.objects.filter(pk=first.pk)
    for change in (
        {"ends_at": F("starts_at")},  # ends when it starts
        {"schedule": None},  # in no session
        {"extra_session_id": first.schedule_id},  # in two sessions at once (references are
        # checked at commit, so the shape rule is what refuses this)
        {"status": "cancelled"},  # cancelled without when and why
        {"status": "cancelled", "cancelled_at": timezone.now()},  # ... without why
        {"cancel_reason": "hospital"},  # why, but not cancelled
        {"cancelled_at": timezone.now()},  # when, but not cancelled
        {"rescheduled_from": first.pk},  # moved to itself
        {"version": -1},
    ):
        with _refused(), transaction.atomic():
            rows.update(**change)
    later = _copy(first, patient_id=other.pk, is_extra=True, rescheduled_from_id=first.pk)
    later.save()
    with _refused(), transaction.atomic():  # one appointment is replaced by one other only
        _copy(first, patient_id=other.pk, is_extra=True, rescheduled_from_id=first.pk).save()
    with transaction.atomic():  # cancelled with when and why is fine
        rows.update(status="cancelled", cancelled_at=timezone.now(), cancel_reason="hospital")


@pytest.mark.django_db
def test_two_receptionists_cannot_double_book_a_doctor(booked):
    """As if two people saved at the same moment, past the service's own check."""
    first, other = booked
    with _refused(), transaction.atomic():
        _copy(first, patient_id=other.pk).save()
    with _refused(), transaction.atomic():  # overlapping part of it is refused too
        _copy(
            first,
            patient_id=other.pk,
            starts_at=first.starts_at + timedelta(minutes=5),
            ends_at=first.ends_at + timedelta(minutes=5),
        ).save()
    # Over the slots, after it, or once the first is cancelled, the same time is fine.
    with transaction.atomic():
        _copy(first, patient_id=other.pk, is_extra=True).save()
        _copy(
            first,
            patient_id=other.pk,
            starts_at=first.ends_at,
            ends_at=first.ends_at + timedelta(minutes=10),
        ).save()
    Appointment.objects.filter(pk=first.pk).update(
        status="cancelled", cancelled_at=timezone.now(), cancel_reason="patient_request"
    )
    with transaction.atomic():
        _copy(
            first, patient_id=other.pk, status="booked", cancelled_at=None, cancel_reason=""
        ).save()


@pytest.mark.django_db
def test_every_database_rule_on_the_schedule_tables_has_a_test():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.conname FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE t.relname = ANY(%s) AND c.contype IN ('c', 'u', 'x')",
            [TABLES],
        )
        found = {name for (name,) in cursor.fetchall()}
        cursor.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = ANY(%s) "
            "AND indexdef LIKE 'CREATE UNIQUE INDEX%%' AND indexname NOT LIKE '%%_pkey'",
            [TABLES],
        )
        found |= {name for (name,) in cursor.fetchall()}
        cursor.execute(
            "SELECT tg.tgname FROM pg_trigger tg JOIN pg_class t ON t.oid = tg.tgrelid "
            "WHERE t.relname = ANY(%s) AND NOT tg.tgisinternal",
            [TABLES],
        )
        found |= {name for (name,) in cursor.fetchall()}
    missing = found - set(RULES)
    assert not missing, f"Add a test that breaks each new rule, and list it in RULES: {missing}"
    gone = set(RULES) - found
    assert not gone, f"These rules are no longer in the database: {gone}"
    names = {name for name in globals() if name.startswith("test_")}
    assert set(RULES.values()) <= names
