"""Doctor OPD schedules and exceptions (HIMS-OPD-001; spec 4.6). All data is synthetic."""

from datetime import time, timedelta

import pytest
from django.test import Client

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.features.models import FeatureFlag
from apps.organizations.dates import hospital_today
from apps.rosters.models import LeaveRequest
from apps.rosters.services import approve_leave, request_leave
from apps.scheduling import services
from apps.scheduling.models import DoctorSchedule, ScheduleException
from apps.staff.models import StaffDepartmentAssignment, StaffMember
from apps.staff.services import end_department_assignment, update_staff_member

from .conftest import API, next_weekday, open_hours

MONDAY, WEDNESDAY, FRIDAY, SATURDAY = 0, 2, 4, 5


def add(client, doctor, department, *, weekdays=(MONDAY,), start="09:00", end="13:00", **extra):
    return client.post(
        f"{API}/doctor-schedules/",
        {
            "staff": str(doctor.pk),
            "department": str(department.pk),
            "weekdays": list(weekdays),
            "start_time": start,
            "end_time": end,
            "valid_from": extra.pop("valid_from", hospital_today().isoformat()),
            **extra,
        },
    )


def week(client, department, start):
    return client.get(
        f"{API}/doctor-schedules/week/", {"department": department.pk, "start": start.isoformat()}
    )


def exception(client, **body):
    return client.post(f"{API}/schedule-exceptions/", body)


def sessions_on(data, staff, day):
    doctor = next(d for d in data["doctors"] if d["staff_id"] == str(staff.pk))
    return next(d for d in doctor["days"] if d["day"] == day.isoformat())


@pytest.fixture
def ravi(doctor, department_a):
    return doctor(department_a, given="Ravi")


@pytest.fixture
def monday():
    return next_weekday(MONDAY)


# --- Weekly sessions ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_head_of_department_adds_weekly_sessions_and_sees_the_slots(
    client_for, hod, ravi, department_a, monday
):
    client = client_for(hod)
    response = add(client, ravi, department_a, weekdays=[MONDAY, WEDNESDAY, FRIDAY], note="Room 4")
    assert response.status_code == 201, response.json()
    assert [s["weekday_label"] for s in response.json()] == ["Monday", "Wednesday", "Friday"]
    assert DoctorSchedule.objects.filter(staff=ravi).count() == 3
    assert AuditEvent.objects.filter(action=AuditAction.DOCTOR_SCHEDULE_ADDED).count() == 3

    data = week(client, department_a, monday).json()
    assert data["can_manage"] is True
    day = sessions_on(data, ravi, monday)
    (session,) = day["sessions"]
    assert session["hours"] == "09:00-13:00"
    assert session["status"] == "open"
    assert session["open_slots"] == 24  # 4 hours of 10-minute slots
    assert session["note"] == "Room 4"
    tuesday = sessions_on(data, ravi, monday + timedelta(days=1))
    assert tuesday["sessions"] == []


@pytest.mark.django_db
def test_a_session_that_cannot_happen_is_refused_with_the_reason(
    client_for, hod, ravi, doctor, department_a
):
    client = client_for(hod)
    open_hours(department_a, opens=time(9), closes=time(17))
    nurse = doctor(department_a, given="Asha", staff_type="nurse")
    cases = [
        (add(client, nurse, department_a), "not a doctor"),
        (add(client, ravi, department_a, start="08:00", end="12:00"), "open 09:00-17:00"),
        (add(client, ravi, department_a, weekdays=[6]), "closed on Sundays"),
        (add(client, ravi, department_a, start="09:00", end="09:05"), "slot does not fit"),
        (
            add(
                client,
                ravi,
                department_a,
                valid_from=(hospital_today() - timedelta(days=1)).isoformat(),
            ),
            "past",
        ),
        (add(client, ravi, department_a, start="12:00", end="10:00"), "end after it starts"),
    ]
    for response, words in cases:
        assert response.status_code == 409, response.json()
        assert words in response.json()["detail"], response.json()["detail"]
    assert DoctorSchedule.objects.count() == 0


@pytest.mark.django_db
def test_one_doctor_cannot_hold_two_sessions_at_once_even_in_two_departments(
    client_for, admin_user, ravi, department_a, department_b
):
    StaffDepartmentAssignment.objects.create(
        organization=department_b.organization,
        staff=ravi,
        department=department_b,
        designation=StaffDepartmentAssignment.objects.get(staff=ravi).designation,
        valid_from=hospital_today() - timedelta(days=10),
    )
    client = client_for(admin_user)
    assert add(client, ravi, department_a, weekdays=[MONDAY, FRIDAY]).status_code == 201
    response = add(
        client, ravi, department_b, weekdays=[WEDNESDAY, FRIDAY], start="12:00", end="15:00"
    )
    assert response.status_code == 409
    assert "Friday" in response.json()["detail"] and "Cardiology" in response.json()["detail"]
    assert DoctorSchedule.objects.filter(department=department_b).count() == 0  # all or none
    # Afternoons are free, and a session that starts after the first one ended does not clash.
    assert (
        add(client, ravi, department_b, weekdays=[FRIDAY], start="13:00", end="16:00").status_code
        == 201
    )
    later = (hospital_today() + timedelta(days=30)).isoformat()
    first = DoctorSchedule.objects.get(department=department_a, weekday=MONDAY)
    services.end_session(
        actor=admin_user,
        schedule_id=first.pk,
        version=first.version,
        last_day=hospital_today() + timedelta(days=29),
        reason="Moves to the afternoon",
    )
    assert add(client, ravi, department_b, weekdays=[MONDAY], valid_from=later).status_code == 201


@pytest.mark.django_db
def test_slots_and_extra_bookings_change_but_hours_are_ended_and_added_again(
    client_for, hod, ravi, department_a, monday
):
    client = client_for(hod)
    (created,) = add(client, ravi, department_a).json()
    url = f"{API}/doctor-schedules/{created['id']}/"
    response = client.patch(
        url, {"version": created["version"], "slot_minutes": 15, "extra_bookings_allowed": 3}
    )
    assert response.status_code == 200, response.json()
    assert response.json()["slot_minutes"] == 15
    assert (
        client.patch(url, {"version": created["version"], "note": "x"}).status_code == 409
    )  # stale
    assert (
        sessions_on(week(client, department_a, monday).json(), ravi, monday)["sessions"][0][
            "open_slots"
        ]
        == 16
    )
    # Ending: the last day runs; a session not started yet is withdrawn.
    schedule = DoctorSchedule.objects.get()
    response = client.post(
        f"{url}end/",
        {
            "version": schedule.version,
            "last_day": hospital_today().isoformat(),
            "reason": "Retiring",
        },
    )
    assert response.status_code == 200, response.json()
    assert response.json()["valid_until"] == hospital_today().isoformat()
    assert sessions_on(week(client, department_a, monday).json(), ravi, monday)["sessions"] == []
    (later,) = add(
        client, ravi, department_a, valid_from=(monday + timedelta(days=7)).isoformat()
    ).json()
    response = client.post(
        f"{API}/doctor-schedules/{later['id']}/end/",
        {
            "version": later["version"],
            "last_day": hospital_today().isoformat(),
            "reason": "Not needed",
        },
    )
    assert response.json()["is_active"] is False
    assert AuditEvent.objects.filter(action=AuditAction.DOCTOR_SCHEDULE_ENDED).count() == 2


# --- Exceptions and the rotas (step 1) ---------------------------------------------------------


@pytest.mark.django_db
def test_approved_leave_on_the_leave_page_takes_the_sessions_off(
    client_for, hod, ravi, department_a, admin_user, monday
):
    client = client_for(hod)
    add(client, ravi, department_a, weekdays=[MONDAY, WEDNESDAY])
    leave = request_leave(
        actor=ravi.user,
        staff=ravi,
        department=department_a,
        leave_type="annual",
        start_date=monday,
        end_date=monday,
    )
    asked = request_leave(
        actor=ravi.user,
        staff=ravi,
        department=department_a,
        leave_type="casual",
        start_date=monday + timedelta(days=2),
        end_date=monday + timedelta(days=2),
    )
    data = week(client, department_a, monday).json()
    assert sessions_on(data, ravi, monday)["sessions"][0]["status"] == "open"
    wednesday = sessions_on(data, ravi, monday + timedelta(days=2))
    assert wednesday["leave_asked"] is True  # asked for, not decided: still open
    approve_leave(
        actor=admin_user, leave_id=leave.pk, version=leave.version, allow_over_balance=True
    )
    (session,) = sessions_on(week(client, department_a, monday).json(), ravi, monday)["sessions"]
    assert session["status"] == "off"
    assert session["open_slots"] == 0
    assert session["off"][0]["kind"] == "rota_leave"
    assert "annual" not in session["off"][0]["reason"].lower()  # the kind of leave stays private
    assert LeaveRequest.objects.filter(pk=asked.pk, status="requested").exists()


@pytest.mark.django_db
def test_part_of_a_day_away_keeps_the_rest_of_the_slots_and_lists_what_it_takes_off(
    client_for, hod, ravi, department_a, monday, front_desk
):
    client = client_for(hod)
    add(client, ravi, department_a)
    response = exception(
        client,
        kind="leave",
        staff=str(ravi.pk),
        department=str(department_a.pk),
        start_date=monday.isoformat(),
        start_time="11:00",
        end_time="13:00",
        reason="Hospital committee",
    )
    assert response.status_code == 201, response.json()
    (affected,) = response.json()["affected"]
    assert affected["hours"] == "09:00-13:00" and affected["status"] == "partly_off"
    (session,) = sessions_on(week(client, department_a, monday).json(), ravi, monday)["sessions"]
    assert session["open_slots"] == 12
    assert session["off"] == [
        {
            "kind": "leave",
            "hours": "11:00-13:00",
            "reason": "Away: Hospital committee",
            "exception_id": response.json()["exception"]["id"],
        }
    ]
    # The front desk sees the slots, not why the doctor is away.
    desk = client_for(front_desk)
    data = week(desk, department_a, monday).json()
    assert data["can_manage"] is False
    assert sessions_on(data, ravi, monday)["sessions"][0]["off"][0]["reason"] == "Away"
    assert data["exceptions"][0]["reason"] == ""
    day = desk.get(f"{API}/availability/", {"doctor": ravi.pk, "date": monday.isoformat()}).json()
    times = [slot["time"] for slot in day["sessions"][0]["slots"]]
    assert times[0] == "09:00" and times[-1] == "10:50" and len(times) == 12
    assert day["sessions"][0]["off"][0]["reason"] == "Away"


@pytest.mark.django_db
def test_holidays_close_a_department_or_the_whole_facility(
    client_for, hod, ravi, doctor, department_a, department_b, make_user, system_roles, monday
):
    client = client_for(hod)
    add(client, ravi, department_a, weekdays=[MONDAY, WEDNESDAY])
    bone = doctor(department_b, given="Meera")
    services.add_sessions(
        actor=None,
        staff=bone,
        department=department_b,
        weekdays=[MONDAY],
        start_time=time(10),
        end_time=time(12),
        valid_from=hospital_today(),
    )
    # A head of department closes only their own department...
    response = exception(
        client,
        kind="holiday",
        department=str(department_a.pk),
        start_date=monday.isoformat(),
        reason="Department training day",
    )
    assert response.status_code == 201, response.json()
    assert len(response.json()["affected"]) == 1
    facility_wide = {
        "kind": "holiday",
        "facility": str(department_a.facility_id),
        "start_date": (monday + timedelta(days=2)).isoformat(),
        "reason": "Diwali",
    }
    assert exception(client, **facility_wide).status_code == 403
    # ...the branch administrator closes the whole facility.
    branch = make_user(role=system_roles["facility-administrator"], facility=department_a.facility)
    response = exception(client_for(branch), **facility_wide)
    assert response.status_code == 201, response.json()
    data = week(client, department_a, monday).json()
    assert sessions_on(data, ravi, monday)["sessions"][0]["off"][0]["reason"] == (
        "Holiday: Department training day"
    )
    wednesday = sessions_on(data, ravi, monday + timedelta(days=2))["sessions"][0]
    assert wednesday["status"] == "off" and wednesday["off"][0]["reason"] == "Holiday: Diwali"
    other = week(client_for(branch), department_b, monday).json()
    assert sessions_on(other, bone, monday)["sessions"][0]["status"] == "open"


@pytest.mark.django_db
def test_an_extra_session_is_added_unless_it_clashes(client_for, hod, ravi, department_a, monday):
    client = client_for(hod)
    add(client, ravi, department_a)
    saturday = monday + timedelta(days=5)
    body = {
        "kind": "extra_session",
        "staff": str(ravi.pk),
        "department": str(department_a.pk),
        "start_date": saturday.isoformat(),
        "start_time": "14:00",
        "end_time": "16:00",
        "slot_minutes": 15,
        "reason": "Health camp follow-ups",
    }
    response = exception(client, **body)
    assert response.status_code == 201, response.json()
    (session,) = sessions_on(week(client, department_a, monday).json(), ravi, saturday)["sessions"]
    assert session["source"] == "extra" and session["open_slots"] == 8
    clash = exception(client, **{**body, "start_time": "15:00", "end_time": "17:00"})
    assert clash.status_code == 409 and "already has a session" in clash.json()["detail"]
    weekly_clash = exception(
        client,
        **{**body, "start_date": monday.isoformat(), "start_time": "12:00", "end_time": "14:00"},
    )
    assert weekly_clash.status_code == 409
    # Cancelled, it is gone from the week; it stays on record.
    item = ScheduleException.objects.get()
    response = client.post(
        f"{API}/schedule-exceptions/{item.pk}/cancel/",
        {"version": item.version, "reason": "Camp postponed"},
    )
    assert response.status_code == 200 and response.json()["status"] == "cancelled"
    assert sessions_on(week(client, department_a, monday).json(), ravi, saturday)["sessions"] == []
    assert AuditEvent.objects.filter(action=AuditAction.SCHEDULE_EXCEPTION_CANCELLED).exists()


@pytest.mark.django_db
def test_exceptions_that_cannot_be_recorded(
    client_for, hod, ravi, doctor, department_a, department_b, monday
):
    client = client_for(hod)
    other = doctor(department_b, given="Kiran")
    cases = [
        (
            {
                "kind": "leave",
                "staff": str(ravi.pk),
                "start_date": monday.isoformat(),
                "reason": "x",
            },
            400,
        ),
        (
            {
                "kind": "leave",
                "staff": str(ravi.pk),
                "department": str(department_a.pk),
                "start_date": (hospital_today() - timedelta(days=1)).isoformat(),
                "reason": "Sick",
            },
            409,
        ),
        (
            {
                "kind": "leave",
                "staff": str(other.pk),  # not in this head's department
                "department": str(department_a.pk),
                "start_date": monday.isoformat(),
                "reason": "Conference",
            },
            409,
        ),
        (
            {
                "kind": "leave",
                "staff": str(ravi.pk),
                "department": str(department_a.pk),
                "start_date": monday.isoformat(),
                "end_date": (monday + timedelta(days=1)).isoformat(),
                "start_time": "09:00",
                "end_time": "10:00",
                "reason": "Conference",
            },
            409,
        ),
        (
            {
                "kind": "extra_session",
                "staff": str(ravi.pk),
                "department": str(department_a.pk),
                "start_date": monday.isoformat(),
                "reason": "No hours given",
            },
            409,
        ),
    ]
    for body, expected in cases:
        response = exception(client, **body)
        assert response.status_code == expected, (body, response.json())
    assert ScheduleException.objects.count() == 0


# --- Who may see and change ---------------------------------------------------------------------


@pytest.mark.django_db
def test_department_scope_the_front_desk_and_the_doctor_themself(
    client_for,
    hod,
    ravi,
    doctor,
    department_a,
    department_b,
    front_desk,
    make_user,
    system_roles,
    monday,
):
    add(client_for(hod), ravi, department_a)
    other_head = make_user(
        role=system_roles["department-head"],
        facility=department_b.facility,
        department=department_b,
    )
    other = client_for(other_head)
    assert week(other, department_a, monday).status_code == 403
    assert add(other, ravi, department_a).status_code == 403
    schedule = DoctorSchedule.objects.get()
    assert (
        other.patch(
            f"{API}/doctor-schedules/{schedule.pk}/", {"version": schedule.version, "note": "x"}
        ).status_code
        == 404
    )
    assert client_for(other_head).get(f"{API}/doctor-schedules/").json() == []
    # The front desk sees every department of its branch, and changes nothing.
    desk = client_for(front_desk)
    assert len(desk.get(f"{API}/doctor-schedules/").json()) == 1
    assert add(desk, ravi, department_a).status_code == 403
    nurse_user = make_user(role=system_roles["basic-staff"], facility=department_a.facility)
    assert week(client_for(nurse_user), department_a, monday).status_code == 403
    # Doctors see their own sessions without any permission.
    mine = client_for(ravi.user).get(f"{API}/my-opd-sessions/", {"start": monday.isoformat()})
    assert mine.status_code == 200
    first = mine.json()["days"][0]
    assert first["sessions"][0]["department_name"] == "Cardiology"
    assert client_for(other_head).get(f"{API}/my-opd-sessions/").json()["has_staff_record"] is False


@pytest.mark.django_db
def test_switched_off_for_the_facility_the_schedules_are_closed(
    client_for, hod, ravi, department_a, monday, admin_user
):
    client = client_for(hod)
    add(client, ravi, department_a)
    FeatureFlag.objects.create(
        organization=department_a.organization,
        facility=department_a.facility,
        key="outpatient.appointments",
        enabled=False,
        reason="Not live here yet",
    )
    assert week(client, department_a, monday).json()["code"] == "FEATURE_DISABLED"
    assert (
        add(client, ravi, department_a, weekdays=[WEDNESDAY]).json()["code"] == "FEATURE_DISABLED"
    )
    assert client.get(f"{API}/doctor-schedules/").json() == []


# --- When people and postings change -------------------------------------------------------------


@pytest.mark.django_db
def test_sessions_end_with_the_posting_and_with_employment(
    client_for, hod, ravi, doctor, department_a, admin_user, monday
):
    add(client_for(hod), ravi, department_a, weekdays=[MONDAY, WEDNESDAY])
    posting = StaffDepartmentAssignment.objects.get(staff=ravi)
    last = hospital_today() + timedelta(days=3)
    end_department_assignment(
        actor=admin_user, staff=ravi, assignment_id=posting.pk, valid_until=last
    )
    assert set(DoctorSchedule.objects.values_list("valid_until", "is_active")) <= {
        (last, True),
        (None, False),
    }
    assert DoctorSchedule.objects.filter(valid_until=last).exists()

    meera = doctor(department_a, given="Meera")
    services.add_sessions(
        actor=None,
        staff=meera,
        department=department_a,
        weekdays=[FRIDAY],
        start_time=time(9),
        end_time=time(11),
        valid_from=hospital_today(),
    )
    meera.refresh_from_db()
    update_staff_member(
        actor=admin_user,
        staff_id=meera.pk,
        version=meera.version,
        employment_status=StaffMember.EmploymentStatus.SUSPENDED,
    )
    friday = next_weekday(FRIDAY)
    data = week(client_for(hod), department_a, friday - timedelta(days=4)).json()
    suspended = sessions_on(data, meera, friday)["sessions"][0]
    assert suspended["status"] == "off" and suspended["off"][0]["kind"] == "not_working"
    meera.refresh_from_db()
    update_staff_member(
        actor=admin_user,
        staff_id=meera.pk,
        version=meera.version,
        employment_status=StaffMember.EmploymentStatus.TERMINATED,
        left_on=hospital_today(),
    )
    schedule = DoctorSchedule.objects.get(staff=meera)
    assert schedule.end_reason == "Employment ended"
    assert schedule.valid_until == hospital_today() - timedelta(days=1) or not schedule.is_active


# --- Admin console --------------------------------------------------------------------------------


@pytest.mark.django_db
def test_console_adds_a_session_and_a_holiday_with_the_same_rules(admin_user, ravi, department_a):
    console = Client()
    console.force_login(admin_user)
    monday = next_weekday(MONDAY)
    form = {
        "staff": ravi.pk,
        "department": department_a.pk,
        "weekday": MONDAY,
        "start_time": "09:00",
        "end_time": "13:00",
        "slot_minutes": 10,
        "extra_bookings_allowed": 2,
        "valid_from": hospital_today().isoformat(),
        "note": "",
    }
    response = console.post("/admin/scheduling/doctorschedule/add/", form)
    assert response.status_code == 302, response.content.decode()[:2000]
    assert DoctorSchedule.objects.get().extra_bookings_allowed == 2
    clash = console.post(
        "/admin/scheduling/doctorschedule/add/",
        {**form, "start_time": "12:00", "end_time": "14:00"},
    )
    assert clash.status_code == 200 and "already has a session" in clash.content.decode()
    holiday = {
        "kind": "holiday",
        "facility": department_a.facility_id,
        "start_date": monday.isoformat(),
        "reason": "Founders' day",
    }
    response = console.post("/admin/scheduling/scheduleexception/add/", holiday)
    assert response.status_code == 302, response.content.decode()[:2000]
    event = AuditEvent.objects.get(action=AuditAction.SCHEDULE_EXCEPTION_ADDED)
    assert event.metadata["kind"] == "holiday"
    assert AuditEvent.objects.filter(action=AuditAction.DOCTOR_SCHEDULE_ADDED).count() == 1
