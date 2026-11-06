"""Shift schedules, on-call rotations and leave (HIMS-STAFF-012). All data is synthetic."""

from datetime import UTC, datetime, time, timedelta

import pytest
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import Client

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.facilities.models import Department
from apps.features.models import FeatureFlag
from apps.organizations.dates import hospital_today
from apps.rosters.models import LeaveRequest, Shift, ShiftType
from apps.rosters.services import add_shifts
from apps.staff.models import Designation, StaffDepartmentAssignment, StaffMember
from apps.staff.services import end_department_assignment, update_staff_member

API = "/api/v1"
_n = iter(range(1, 10_000))


@pytest.fixture
def client_for(client_for):
    """The shared fixture, sending JSON by default (the API accepts nothing else)."""

    def factory(user=None):
        client = client_for(user)
        client.default_format = "json"
        return client

    return factory


@pytest.fixture
def department_b(facility_a):
    return Department.objects.create(
        organization_id=facility_a.organization_id,
        facility=facility_a,
        code="ortho",
        name="Orthopaedics",
        department_type=Department.DepartmentType.CLINICAL,
    )


@pytest.fixture
def person(organization, make_user):
    """A working staff member with an account, posted in the given department."""

    def factory(department, *, given="Asha", account=True):
        n = next(_n)
        user = (
            make_user(email=f"rota{n}@synthetic.test", display_name=f"{given} Rota{n}")
            if account
            else None
        )
        staff = StaffMember.objects.create(
            organization=organization,
            user=user,
            employee_number=f"EMP-ROTA-{n}",
            given_name=given,
            family_name=f"Rota{n}",
            staff_type="nurse",
            joined_on="2026-01-05",
        )
        StaffDepartmentAssignment.objects.create(
            organization=organization,
            staff=staff,
            department=department,
            designation=Designation.objects.order_by("seniority").first(),
            valid_from=hospital_today() - timedelta(days=60),
            is_primary=True,
        )
        return staff

    return factory


@pytest.fixture
def hod(make_user, system_roles, department_a):
    return make_user(
        role=system_roles["department-head"],
        facility=department_a.facility,
        department=department_a,
        display_name="Synthetic Head",
    )


def shift_type(code="morning"):
    return ShiftType.objects.get(code=code)


def tomorrow():
    return hospital_today() + timedelta(days=1)


def plan(client, staff, department, *, code="morning", day=None, **extra):
    return client.post(
        f"{API}/shifts/",
        {
            "staff": str(staff.pk),
            "department": str(department.pk),
            "shift_type": str(shift_type(code).pk),
            "from_date": (day or tomorrow()).isoformat(),
            **extra,
        },
        format="json",
    )


# --- Shift types -------------------------------------------------------------------------------


@pytest.mark.django_db
def test_standard_shift_types_and_their_times(facility_a):
    assert ShiftType.objects.count() == 8
    night = shift_type("night")
    assert night.minutes == 12 * 60
    start, end = night.window(datetime(2026, 11, 9).date(), facility_a_zone(facility_a))
    assert (start.hour, end.hour, (end.date() - start.date()).days) == (20, 8, 1)
    assert start.astimezone(UTC) == datetime(2026, 11, 9, 14, 30, tzinfo=UTC)  # India
    assert shift_type("on-call-24h").minutes == 24 * 60


def facility_a_zone(facility):
    from zoneinfo import ZoneInfo

    return ZoneInfo(facility.timezone)


@pytest.mark.django_db
def test_shift_types_are_kept_by_a_hospital_wide_grant_only(client_for, admin_user, hod):
    body = {
        "code": "theatre-long",
        "name": "Theatre long day",
        "kind": "shift",
        "start_time": "07:30",
        "end_time": "20:30",
    }
    assert client_for(hod).post(f"{API}/shift-types/", body, format="json").status_code == 403
    created = client_for(admin_user).post(f"{API}/shift-types/", body, format="json")
    assert created.status_code == 201 and created.json()["is_custom"] is True
    pk, version = created.json()["id"], created.json()["version"]
    assert client_for(hod).get(f"{API}/shift-types/").status_code == 200
    stale = {"version": version + 1, "name": "x"}
    url = f"{API}/shift-types/{pk}/"
    assert client_for(admin_user).patch(url, stale, format="json").status_code == 409
    renamed = client_for(admin_user).patch(
        url, {"version": version, "name": "Theatre day"}, format="json"
    )
    assert renamed.json()["name"] == "Theatre day"
    assert AuditEvent.objects.filter(action=AuditAction.SHIFT_TYPE_UPDATED).exists()


# --- Planning shifts -----------------------------------------------------------------------------


@pytest.mark.django_db
def test_head_plans_shifts_in_their_own_department_only(
    client_for, hod, person, department_a, department_b
):
    asha = person(department_a)
    ravi = person(department_b, given="Ravi")
    client = client_for(hod)
    response = plan(client, asha, department_a, code="night", note="Covering ICU")
    assert response.status_code == 201, response.json()
    [shift] = response.json()["created"]
    assert shift["kind"] == "shift" and shift["note"] == "Covering ICU"
    assert plan(client, ravi, department_b).status_code == 403
    event = AuditEvent.objects.get(action=AuditAction.SHIFT_ADDED)
    assert event.resource_id == shift["id"]


@pytest.mark.django_db
def test_basic_staff_see_the_rota_but_cannot_plan(
    client_for, make_user, system_roles, person, department_a
):
    colleague = make_user(
        role=system_roles["basic-staff"], facility=department_a.facility, department=department_a
    )
    client = client_for(colleague)
    assert plan(client, person(department_a), department_a).status_code == 403
    rota = client.get(f"{API}/rota/", {"department": str(department_a.pk)})
    assert rota.status_code == 200 and rota.json()["can_manage"] is False


@pytest.mark.django_db
def test_several_days_with_reasons_for_the_days_skipped(
    client_for, admin_user, person, department_a, department_b
):
    asha = person(department_a)
    start = tomorrow()
    add_shifts(
        actor=admin_user,
        staff=asha,
        department=department_a,
        shift_type=shift_type("general"),
        from_date=start + timedelta(days=1),
        to_date=start + timedelta(days=1),
    )
    LeaveRequest.objects.create(
        organization_id=asha.organization_id,
        staff=asha,
        facility_id=department_a.facility_id,
        department=department_a,
        leave_type="annual",
        start_date=start + timedelta(days=2),
        end_date=start + timedelta(days=2),
        status=LeaveRequest.Status.APPROVED,
    )
    response = plan(
        client_for(admin_user),
        asha,
        department_a,
        day=start,
        to_date=(start + timedelta(days=3)).isoformat(),
    )
    body = response.json()
    assert response.status_code == 201
    assert len(body["created"]) == 2
    reasons = {row["on_date"]: row["reason"] for row in body["skipped"]}
    assert "already has General" in reasons[(start + timedelta(days=1)).isoformat()]
    assert "approved leave" in reasons[(start + timedelta(days=2)).isoformat()]
    other = plan(client_for(admin_user), asha, department_b, day=start + timedelta(days=5))
    assert other.status_code == 409 and "not posted in Orthopaedics" in other.json()["detail"]


@pytest.mark.django_db
def test_weekdays_only_and_limits(client_for, admin_user, person, department_a):
    asha = person(department_a)
    monday = tomorrow() + timedelta(days=7 - tomorrow().weekday())
    response = plan(
        client_for(admin_user),
        asha,
        department_a,
        day=monday,
        to_date=(monday + timedelta(days=6)).isoformat(),
        weekdays=[0, 2, 4],
    )
    assert [s["on_date"] for s in response.json()["created"]] == [
        (monday + timedelta(days=n)).isoformat() for n in (0, 2, 4)
    ]
    too_long = plan(
        client_for(admin_user),
        asha,
        department_a,
        day=monday,
        to_date=(monday + timedelta(days=70)).isoformat(),
    )
    assert too_long.status_code == 409 and too_long.json()["code"] == "TOO_MANY_DAYS"
    past = plan(
        client_for(admin_user), asha, department_a, day=hospital_today() - timedelta(days=2)
    )
    assert past.status_code == 409 and "already over" in past.json()["detail"]


@pytest.mark.django_db
def test_the_database_refuses_two_overlapping_shifts(admin_user, person, department_a):
    asha = person(department_a)
    [shift] = add_shifts(
        actor=admin_user,
        staff=asha,
        department=department_a,
        shift_type=shift_type("night"),
        from_date=tomorrow(),
        to_date=tomorrow(),
    )[0]
    with pytest.raises(IntegrityError), transaction.atomic():
        Shift.objects.create(
            organization_id=shift.organization_id,
            staff=asha,
            facility_id=shift.facility_id,
            department=department_a,
            shift_type=shift_type("on-call-night"),
            on_date=shift.on_date,
            starts_at=shift.starts_at + timedelta(hours=2),
            ends_at=shift.ends_at + timedelta(hours=2),
        )


@pytest.mark.django_db
def test_cancel_needs_a_reason_and_the_current_version(client_for, hod, person, department_a):
    shift = plan(client_for(hod), person(department_a), department_a).json()["created"][0]
    url = f"{API}/shifts/{shift['id']}/cancel/"
    client = client_for(hod)
    assert client.post(url, {"version": shift["version"] + 1, "reason": "x"}).status_code == 409
    assert client.post(url, {"version": shift["version"], "reason": " "}).status_code == 400
    done = client.post(url, {"version": shift["version"], "reason": "Swapped with Ravi"})
    assert (
        done.json()["status"] == "cancelled" and done.json()["cancel_reason"] == "Swapped with Ravi"
    )
    again = client.post(url, {"version": done.json()["version"], "reason": "again"})
    assert again.json()["code"] == "ALREADY_CANCELLED"


@pytest.mark.django_db
def test_copy_a_week_skips_people_on_leave(client_for, hod, person, department_a):
    asha, ravi = person(department_a), person(department_a, given="Ravi")
    monday = tomorrow() + timedelta(days=7 - tomorrow().weekday())
    for staff in (asha, ravi):
        plan(client_for(hod), staff, department_a, day=monday, to_date=str(monday + timedelta(4)))
    LeaveRequest.objects.create(
        organization_id=ravi.organization_id,
        staff=ravi,
        facility_id=department_a.facility_id,
        department=department_a,
        leave_type="annual",
        start_date=monday + timedelta(days=7),
        end_date=monday + timedelta(days=13),
        status=LeaveRequest.Status.APPROVED,
    )
    response = client_for(hod).post(
        f"{API}/shifts/copy-week/",
        {
            "department": str(department_a.pk),
            "from_start": monday.isoformat(),
            "to_start": (monday + timedelta(days=7)).isoformat(),
        },
        format="json",
    )
    body = response.json()
    assert response.status_code == 201
    assert len(body["created"]) == 5 and len(body["skipped"]) == 5
    assert all("approved leave" in row["reason"] for row in body["skipped"])
    wrong = client_for(hod).post(
        f"{API}/shifts/copy-week/",
        {
            "department": str(department_a.pk),
            "from_start": monday.isoformat(),
            "to_start": (monday + timedelta(days=3)).isoformat(),
        },
        format="json",
    )
    assert wrong.json()["code"] == "INVALID_WEEK"


# --- Rota screens ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_week_shows_shifts_and_who_is_away_but_not_why(
    client_for, make_user, system_roles, hod, person, department_a
):
    asha, ravi = person(department_a), person(department_a, given="Ravi")
    monday = tomorrow() + timedelta(days=7 - tomorrow().weekday())
    plan(client_for(hod), asha, department_a, day=monday, code="on-call-24h")
    LeaveRequest.objects.create(
        organization_id=ravi.organization_id,
        staff=ravi,
        facility_id=department_a.facility_id,
        department=department_a,
        leave_type="sick",
        start_date=monday,
        end_date=monday + timedelta(days=1),
        status=LeaveRequest.Status.APPROVED,
    )
    query = {"department": str(department_a.pk), "start": monday.isoformat()}
    colleague = make_user(
        role=system_roles["basic-staff"], facility=department_a.facility, department=department_a
    )
    seen = client_for(colleague).get(f"{API}/rota/", query).json()
    people = {p["name"]: p for p in seen["people"]}
    assert len(seen["days"]) == 7
    assert people[f"Asha {asha.family_name}"]["shifts"][0]["kind"] == "on_call"
    away = people[f"Ravi {ravi.family_name}"]["away"][0]
    assert away["status"] == "approved" and away["leave_type"] is None  # not why
    by_head = client_for(hod).get(f"{API}/rota/", query).json()
    head_view = {p["name"]: p for p in by_head["people"]}
    assert head_view[f"Ravi {ravi.family_name}"]["away"][0]["leave_type_label"] == "Sick leave"
    assert by_head["can_manage"] is True


@pytest.mark.django_db
def test_rota_closed_when_the_feature_is_off(client_for, admin_user, hod, person, department_a):
    FeatureFlag.objects.create(
        organization_id=department_a.organization_id,
        key="staff.rotas",
        facility=department_a.facility,
        enabled=False,
        reason="Using the old system for now",
    )
    query = {"department": str(department_a.pk)}
    assert client_for(hod).get(f"{API}/rota/", query).json()["code"] == "FEATURE_DISABLED"
    assert plan(client_for(hod), person(department_a), department_a).status_code == 409


@pytest.mark.django_db
def test_on_call_now_lists_only_departments_you_may_see(
    client_for, hod, admin_user, person, department_a, department_b, monkeypatch
):
    asha, ravi = person(department_a), person(department_b, given="Ravi")
    for staff, department in ((asha, department_a), (ravi, department_b)):
        add_shifts(
            actor=admin_user,
            staff=staff,
            department=department,
            shift_type=shift_type("on-call-24h"),
            from_date=tomorrow(),
            to_date=tomorrow(),
        )
    later = Shift.objects.first().starts_at + timedelta(hours=3)
    monkeypatch.setattr("django.utils.timezone.now", lambda: later)
    mine = client_for(hod).get(f"{API}/rota/now/").json()
    assert [s["staff_name"] for s in mine["on_call"]] == [f"Asha {asha.family_name}"]
    everyone = client_for(admin_user).get(f"{API}/rota/now/").json()
    assert len(everyone["on_call"]) == 2 and everyone["working"] == []


# --- Leave -------------------------------------------------------------------------------------


def ask(client, department, *, start, days=1, leave_type="annual", reason=""):
    return client.post(
        f"{API}/my-leave-requests/",
        {
            "department": str(department.pk),
            "leave_type": leave_type,
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=days - 1)).isoformat(),
            "reason": reason,
        },
        format="json",
    )


@pytest.mark.django_db
def test_ask_for_leave_and_the_head_is_emailed(client_for, hod, person, department_a):
    asha = person(department_a)
    mail.outbox.clear()
    response = ask(
        client_for(asha.user), department_a, start=tomorrow() + timedelta(days=10), days=3
    )
    assert response.status_code == 201, response.json()
    assert response.json()["status"] == "requested" and response.json()["days"] == 3
    [email] = mail.outbox
    assert email.to == [hod.email] and "Leave to decide" in email.subject
    overlap = ask(client_for(asha.user), department_a, start=tomorrow() + timedelta(days=11))
    assert overlap.json()["code"] == "LEAVE_OVERLAP"
    waiting = client_for(hod).get(f"{API}/leave-requests/").json()
    assert [w["id"] for w in waiting] == [response.json()["id"]]


@pytest.mark.django_db
def test_people_without_a_staff_record_have_no_rota(client_for, make_user, department_a):
    account = make_user()
    assert client_for(account).get(f"{API}/my-schedule/").json()["has_staff_record"] is False
    refused = ask(client_for(account), department_a, start=tomorrow())
    assert refused.json()["code"] == "NO_STAFF_RECORD"


@pytest.mark.django_db
def test_approving_leave_over_planned_shifts(client_for, hod, person, department_a):
    asha = person(department_a)
    start = tomorrow() + timedelta(days=3)
    plan(client_for(hod), asha, department_a, day=start, to_date=str(start + timedelta(days=1)))
    leave = ask(client_for(asha.user), department_a, start=start, days=2).json()
    url = f"{API}/leave-requests/{leave['id']}/approve/"
    detail = client_for(hod).get(f"{API}/leave-requests/{leave['id']}/").json()
    assert len(detail["conflicting_shifts"]) == 2
    blocked = client_for(hod).post(url, {"version": leave["version"]}, format="json")
    assert blocked.json()["code"] == "LEAVE_SHIFT_CONFLICT"
    mail.outbox.clear()
    approved = client_for(hod).post(
        url, {"version": leave["version"], "cancel_shifts": True, "note": "Enjoy"}, format="json"
    )
    assert approved.json()["status"] == "approved"
    assert not Shift.objects.filter(staff=asha, status="scheduled").exists()
    assert [m.to for m in mail.outbox] == [[asha.user.email]]
    assert AuditEvent.objects.filter(action=AuditAction.SHIFT_CANCELLED).count() == 2


@pytest.mark.django_db
def test_nobody_decides_their_own_leave(client_for, make_user, system_roles, person, department_a):
    head = person(department_a, given="Head")
    from apps.access_control.services import assign_role

    assign_role(
        actor=None,
        user=head.user,
        role=system_roles["department-head"],
        facility=department_a.facility,
        department=department_a,
    )
    leave = ask(client_for(head.user), department_a, start=tomorrow()).json()
    own = client_for(head.user).post(
        f"{API}/leave-requests/{leave['id']}/approve/", {"version": leave["version"]}
    )
    assert own.json()["code"] == "SELF_DECISION"


@pytest.mark.django_db
def test_refusing_needs_a_reason(client_for, hod, person, department_a):
    asha = person(department_a)
    leave = ask(client_for(asha.user), department_a, start=tomorrow()).json()
    url = f"{API}/leave-requests/{leave['id']}/reject/"
    assert client_for(hod).post(url, {"version": leave["version"]}).json()["code"] == (
        "REASON_REQUIRED"
    )
    refused = client_for(hod).post(url, {"version": leave["version"], "note": "Short-staffed"})
    assert refused.json()["status"] == "rejected"
    assert refused.json()["decided_by_name"] == "Synthetic Head"


@pytest.mark.django_db
def test_withdrawing_your_own_leave(client_for, hod, person, department_a):
    asha = person(department_a)
    leave = ask(client_for(asha.user), department_a, start=tomorrow() + timedelta(days=5)).json()
    url = f"{API}/my-leave-requests/{leave['id']}/cancel/"
    other = person(department_a, given="Ravi")
    assert client_for(other.user).post(url, {"version": 1, "reason": "x"}).status_code == 404
    done = client_for(asha.user).post(url, {"version": leave["version"], "reason": "Plans changed"})
    assert done.json()["status"] == "cancelled"
    schedule = client_for(asha.user).get(f"{API}/my-schedule/").json()
    assert schedule["leave"][0]["status"] == "cancelled"
    assert schedule["postings"][0]["department_name"] == "Cardiology"


@pytest.mark.django_db
def test_started_leave_is_ended_by_the_head_not_the_person(
    client_for, hod, admin_user, person, department_a
):
    asha = person(department_a)
    leave = LeaveRequest.objects.create(
        organization_id=asha.organization_id,
        staff=asha,
        facility_id=department_a.facility_id,
        department=department_a,
        leave_type="annual",
        start_date=hospital_today(),
        end_date=hospital_today() + timedelta(days=4),
        status=LeaveRequest.Status.APPROVED,
    )
    own = client_for(asha.user).post(
        f"{API}/my-leave-requests/{leave.pk}/cancel/", {"version": 1, "reason": "Back early"}
    )
    assert own.json()["code"] == "LEAVE_STARTED"
    by_head = client_for(hod).post(
        f"{API}/leave-requests/{leave.pk}/cancel/", {"version": 1, "reason": "Back early"}
    )
    assert by_head.json()["status"] == "cancelled"


@pytest.mark.django_db
def test_approver_records_leave_for_someone(client_for, hod, person, department_a, department_b):
    asha, ravi = person(department_a), person(department_b, given="Ravi")
    body = {
        "staff": str(asha.pk),
        "department": str(department_a.pk),
        "leave_type": "sick",
        "start_date": (hospital_today() - timedelta(days=2)).isoformat(),
        "end_date": hospital_today().isoformat(),
    }
    recorded = client_for(hod).post(f"{API}/leave-requests/", body, format="json")
    assert recorded.status_code == 201 and recorded.json()["requested_by_name"] == "Synthetic Head"
    elsewhere = {**body, "staff": str(ravi.pk), "department": str(department_b.pk)}
    assert (
        client_for(hod).post(f"{API}/leave-requests/", elsewhere, format="json").status_code == 403
    )
    too_old = {**body, "start_date": (hospital_today() - timedelta(days=40)).isoformat()}
    assert client_for(hod).post(f"{API}/leave-requests/", too_old, format="json").json()[
        "code"
    ] == ("TOO_FAR_BACK")


@pytest.mark.django_db
def test_the_database_refuses_overlapping_leave(person, department_a):
    asha = person(department_a)
    common = {
        "organization_id": asha.organization_id,
        "staff": asha,
        "facility_id": department_a.facility_id,
        "department": department_a,
        "leave_type": "annual",
    }
    LeaveRequest.objects.create(start_date=tomorrow(), end_date=tomorrow() + timedelta(3), **common)
    with pytest.raises(IntegrityError), transaction.atomic():
        LeaveRequest.objects.create(
            start_date=tomorrow() + timedelta(3), end_date=tomorrow() + timedelta(5), **common
        )


# --- When people stop working or move -----------------------------------------------------------


@pytest.mark.django_db
def test_leaving_cancels_future_shifts_and_leave(admin_user, person, department_a):
    asha = person(department_a)
    add_shifts(
        actor=admin_user,
        staff=asha,
        department=department_a,
        shift_type=shift_type("morning"),
        from_date=tomorrow(),
        to_date=tomorrow() + timedelta(days=2),
    )
    leave = LeaveRequest.objects.create(
        organization_id=asha.organization_id,
        staff=asha,
        facility_id=department_a.facility_id,
        department=department_a,
        leave_type="annual",
        start_date=tomorrow() + timedelta(days=10),
        end_date=tomorrow() + timedelta(days=11),
    )
    update_staff_member(
        actor=admin_user, staff_id=asha.pk, version=asha.version, employment_status="terminated"
    )
    assert not Shift.objects.filter(staff=asha, status="scheduled").exists()
    assert Shift.objects.filter(staff=asha).first().cancel_reason == (
        "Employment status changed to terminated"
    )
    leave.refresh_from_db()
    assert leave.status == "cancelled"


@pytest.mark.django_db
def test_ending_a_posting_cancels_shifts_after_its_last_day(admin_user, person, department_a):
    asha = person(department_a)
    add_shifts(
        actor=admin_user,
        staff=asha,
        department=department_a,
        shift_type=shift_type("morning"),
        from_date=tomorrow(),
        to_date=tomorrow() + timedelta(days=3),
    )
    posting = asha.department_assignments.get()
    end_department_assignment(
        actor=admin_user, staff=asha, assignment_id=posting.pk, valid_until=tomorrow()
    )
    kept = Shift.objects.filter(staff=asha, status="scheduled").values_list("on_date", flat=True)
    assert list(kept) == [tomorrow()]


# --- Admin console -----------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_console_plans_shifts_and_decides_leave_with_the_same_rules(
    admin_user, hod, person, department_a
):
    console = Client()
    console.force_login(admin_user)
    asha = person(department_a)
    form = {
        "staff": str(asha.pk),
        "department": str(department_a.pk),
        "shift_type": str(shift_type("evening").pk),
        "on_date": tomorrow().isoformat(),
        "note": "",
    }
    assert console.post("/admin/rosters/shift/add/", form).status_code == 302
    clash = console.post(
        "/admin/rosters/shift/add/", {**form, "shift_type": str(shift_type("day-12h").pk)}
    )
    assert clash.status_code == 200 and b"already has Evening" in clash.content
    leave = {
        "staff": str(asha.pk),
        "department": str(department_a.pk),
        "leave_type": "annual",
        "start_date": (tomorrow() + timedelta(days=20)).isoformat(),
        "end_date": (tomorrow() + timedelta(days=21)).isoformat(),
        "reason": "",
    }
    assert console.post("/admin/rosters/leaverequest/add/", leave).status_code == 302
    again = console.post("/admin/rosters/leaverequest/add/", leave)
    assert b"already has leave" in again.content
    recorded = LeaveRequest.objects.get(staff=asha)
    console.post(
        "/admin/rosters/leaverequest/",
        {"action": "approve_selected", "_selected_action": [str(recorded.pk)]},
    )
    recorded.refresh_from_db()
    assert recorded.status == "approved" and recorded.decided_by == admin_user
    assert time(17) == shift_type("general").end_time
