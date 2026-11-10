"""Minimum staffing per shift and gap alerts (HIMS-STAFF-015; spec 4.3). All data is synthetic."""

from datetime import date, time, timedelta

import pytest
from django.core import mail
from django.db import IntegrityError, transaction

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.features.catalog import F
from apps.features.services import ensure_hospital_rows, set_feature
from apps.notifications.models import Notification
from apps.organizations.dates import hospital_today
from apps.rosters.models import Shift, ShiftType, StaffingGapAlert, StaffingRequirement
from apps.rosters.services import add_shifts
from apps.rosters.staffing import gaps, send_staffing_gap_alerts
from common.admin.tests.test_console_additions import console

API = "/api/v1/staffing-requirements/"


@pytest.fixture
def client(client_for, admin_user):
    client = client_for(admin_user)
    client.default_format = "json"
    return client


@pytest.fixture
def morning(db):
    return ShiftType.objects.create(
        code="early-test", name="Early", start_time=time(8), end_time=time(14)
    )


def _next(weekday: int) -> date:
    """The next such weekday, at least a day away so its shifts are never over."""
    day = hospital_today() + timedelta(days=1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day


def _require(client, department, shift_type, minimum=2, **extra):
    body = {
        "department": str(department.pk),
        "shift_type": str(shift_type.pk),
        "minimum": minimum,
        **extra,
    }
    return client.post(API, body)


def _plan(actor, staff, department, shift_type, day):
    created, skipped = add_shifts(
        actor=actor,
        staff=staff,
        department=department,
        shift_type=shift_type,
        from_date=day,
        to_date=day,
    )
    assert created, skipped


@pytest.mark.django_db
def test_set_a_minimum_and_see_it(client, department_a, morning):
    response = _require(client, department_a, morning, staff_type="nurse", applies_on="weekends")
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["minimum"] == 2 and body["staff_type_label"] == "Nurse"
    assert body["applies_on_label"] == "Saturday and Sunday"
    listed = client.get(f"{API}?department={department_a.pk}").json()
    assert [row["id"] for row in listed] == [body["id"]]
    assert AuditEvent.objects.filter(action=AuditAction.STAFFING_REQUIREMENT_CREATED).count() == 1


@pytest.mark.django_db
def test_minimum_must_be_at_least_one(client, department_a, morning):
    assert _require(client, department_a, morning, minimum=0).status_code == 400


@pytest.mark.django_db
def test_two_minimums_cannot_count_the_same_people_on_the_same_days(client, department_a, morning):
    assert _require(client, department_a, morning, applies_on="weekdays").status_code == 201
    assert _require(client, department_a, morning, applies_on="weekends").status_code == 201
    every = _require(client, department_a, morning, applies_on="every_day")
    assert every.status_code == 409 and every.json()["code"] == "DUPLICATE_REQUIREMENT"
    # A different kind of person is a separate minimum.
    assert _require(client, department_a, morning, staff_type="nurse").status_code == 201


@pytest.mark.django_db
def test_change_and_switch_off_with_the_current_version(client, department_a, morning):
    row = _require(client, department_a, morning).json()
    url = f"{API}{row['id']}/"
    changed = client.patch(url, {"version": row["version"], "minimum": 3})
    assert changed.status_code == 200 and changed.json()["minimum"] == 3
    assert client.patch(url, {"version": row["version"], "minimum": 4}).status_code == 409
    off = client.patch(url, {"version": changed.json()["version"], "is_active": False})
    assert off.json()["is_active"] is False
    assert gaps(department_a, _next(0), _next(0)) == []


@pytest.mark.django_db
def test_gaps_count_only_who_is_planned_and_who_counts(
    client,
    admin_user,
    department_a,
    morning,
    person,
):
    _require(client, department_a, morning, minimum=2, staff_type="nurse")
    monday = _next(0)
    found = gaps(department_a, monday, monday)
    assert [(g["planned"], g["short_by"]) for g in found] == [(0, 2)]
    assert found[0]["staff_type_label"] == "Nurse"
    nurse = person(department_a)
    _plan(admin_user, nurse, department_a, morning, monday)
    assert [g["short_by"] for g in gaps(department_a, monday, monday)] == [1]
    # A cancelled shift no longer counts.
    Shift.objects.filter(staff=nurse).update(status="cancelled")
    assert [g["short_by"] for g in gaps(department_a, monday, monday)] == [2]


@pytest.mark.django_db
def test_someone_of_another_kind_does_not_fill_a_kind_gap(
    client,
    admin_user,
    department_a,
    morning,
    person,
):
    _require(client, department_a, morning, minimum=1, staff_type="doctor")
    monday = _next(0)
    _plan(admin_user, person(department_a), department_a, morning, monday)  # a nurse
    assert [g["short_by"] for g in gaps(department_a, monday, monday)] == [1]


@pytest.mark.django_db
def test_anyone_counts_when_no_kind_is_set(
    client,
    admin_user,
    department_a,
    morning,
    person,
):
    _require(client, department_a, morning, minimum=1)
    monday = _next(0)
    _plan(admin_user, person(department_a), department_a, morning, monday)
    assert gaps(department_a, monday, monday) == []


@pytest.mark.django_db
def test_weekday_and_weekend_minimums_apply_on_their_days(client, department_a, morning):
    _require(client, department_a, morning, minimum=4, applies_on="weekdays")
    _require(client, department_a, morning, minimum=1, applies_on="weekends")
    monday, sunday = _next(0), _next(6)
    assert [g["minimum"] for g in gaps(department_a, monday, monday)] == [4]
    assert [g["minimum"] for g in gaps(department_a, sunday, sunday)] == [1]


@pytest.mark.django_db
def test_a_gap_never_blocks_planning(
    client,
    admin_user,
    department_a,
    morning,
    person,
):
    _require(client, department_a, morning, minimum=5)
    _plan(admin_user, person(department_a), department_a, morning, _next(0))


@pytest.mark.django_db
def test_the_rota_week_shows_gaps_from_today_on(client, department_a, morning):
    _require(client, department_a, morning, minimum=1)
    monday = _next(0)
    body = client.get(f"/api/v1/rota/?department={department_a.pk}&start={monday}").json()
    assert len(body["staffing_gaps"]) == 7
    assert body["staffing_gaps"][0]["shift_type_name"] == "Early"
    past = monday - timedelta(days=28)
    old = client.get(f"/api/v1/rota/?department={department_a.pk}&start={past}").json()
    assert old["staffing_gaps"] == []  # a past gap cannot be filled


@pytest.mark.django_db
def test_alert_goes_to_planners_once_and_names_nobody(
    client, department_a, morning, make_user, system_roles, facility_a
):
    head = make_user(
        email="head@synthetic.test",
        role=system_roles["department-head"],
        facility=facility_a,
        department=department_a,
    )
    make_user(
        email="basic@synthetic.test",
        role=system_roles["basic-staff"],
        facility=facility_a,
        department=department_a,
    )
    _require(client, department_a, morning, minimum=2, staff_type="nurse")
    mail.outbox.clear()
    today = hospital_today()
    assert send_staffing_gap_alerts(today) == 7
    sent = mail.outbox[-1]
    assert head.email in sent.to and "basic@synthetic.test" not in sent.to
    assert department_a.name in sent.subject and "7 shift(s)" in sent.subject
    assert "0 of 2 nurse planned" in sent.body
    assert Notification.objects.get(template="rosters.staffing_gaps").category == "staff"
    assert StaffingGapAlert.objects.count() == 7
    assert AuditEvent.objects.filter(action=AuditAction.STAFFING_GAP_ALERT_SENT).count() == 1
    # Run again: nothing new to tell.
    mail.outbox.clear()
    assert send_staffing_gap_alerts(today) == 0
    assert mail.outbox == []
    # The next day brings one new day into the window.
    assert send_staffing_gap_alerts(today + timedelta(days=1)) == 1


@pytest.mark.django_db
def test_no_alert_when_the_rota_feature_is_off(
    client, admin_user, department_a, morning, organization, facility_a
):
    ensure_hospital_rows(organization)
    _require(client, department_a, morning)
    set_feature(
        actor=admin_user, key=F.ROTAS, facility=facility_a, enabled=False, reason="Off", version=0
    )
    assert send_staffing_gap_alerts() == 0
    assert _require(client, department_a, morning, staff_type="nurse").status_code == 409


@pytest.mark.django_db
def test_a_department_grant_sets_only_its_department(
    client_for,
    make_user,
    system_roles,
    facility_a,
    department_a,
    department_b,
    morning,
):
    head = client_for(
        make_user(
            role=system_roles["department-head"], facility=facility_a, department=department_a
        )
    )
    head.default_format = "json"
    assert _require(head, department_a, morning).status_code == 201
    assert _require(head, department_b, morning).status_code == 403
    basic = client_for(make_user(role=system_roles["basic-staff"], facility=facility_a))
    basic.default_format = "json"
    assert basic.get(API).status_code == 200  # rota.view reads the numbers
    assert _require(basic, department_a, morning, staff_type="nurse").status_code == 403


@pytest.mark.django_db
def test_the_database_refuses_a_minimum_of_zero(department_a, morning):
    with pytest.raises(IntegrityError), transaction.atomic():
        StaffingRequirement.objects.create(
            organization_id=department_a.organization_id,
            facility_id=department_a.facility_id,
            department=department_a,
            shift_type=morning,
            minimum=0,
        )


@pytest.mark.django_db
def test_console_sets_a_minimum_and_lists_gaps(admin_user, department_a, morning):
    client = console(admin_user, confirmed=True)
    add = "/admin/rosters/staffingrequirement/add/"
    assert client.get(add).status_code == 200
    response = client.post(
        add,
        {
            "department": str(department_a.pk),
            "shift_type": str(morning.pk),
            "staff_type": "",
            "applies_on": "every_day",
            "minimum": 2,
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    row = StaffingRequirement.objects.get()
    assert row.facility_id == department_a.facility_id
    listing = client.get("/admin/rosters/staffingrequirement/").content.decode()
    assert "/admin/rosters/staffingrequirement/gaps/" in listing
    page = client.get("/admin/rosters/staffingrequirement/gaps/").content.decode()
    assert "Early" in page and department_a.name in page
    assert client.get("/admin/rosters/staffinggapalert/").status_code == 200
