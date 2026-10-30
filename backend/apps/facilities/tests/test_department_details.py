"""Department head, services and opening hours (HIMS-FAC-007); catalog screens (HIMS-STAFF-010).
All data is synthetic."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.facilities.models import DepartmentService
from apps.staff.models import Designation, Specialty, StaffDepartmentAssignment, StaffMember

API = "/api/v1"


def _staff(organization, number="EMP-H1", **extra):
    return StaffMember.objects.create(
        organization=organization,
        employee_number=number,
        given_name="Asha",
        family_name="Rao",
        staff_type="doctor",
        joined_on="2026-01-05",
        **extra,
    )


def _post(staff, department, **extra):
    return StaffDepartmentAssignment.objects.create(
        organization_id=staff.organization_id,
        staff=staff,
        department=department,
        designation=Designation.objects.filter(is_active=True, category="medical").last(),
        valid_from="2026-01-05",
        **extra,
    )


def _set_head(client, department, head):
    department.refresh_from_db()
    return client.patch(
        f"{API}/departments/{department.pk}/",
        {"version": department.version, "head": str(head.pk) if head else None},
        format="json",
    )


# --- Head of department -----------------------------------------------------------------------


@pytest.mark.django_db
def test_head_must_be_posted_and_working(client_for, admin_user, organization, department_a):
    client = client_for(admin_user)
    doctor = _staff(organization)
    refused = _set_head(client, department_a, doctor)
    assert refused.status_code == 400
    assert "currently be posted" in str(refused.json())

    _post(doctor, department_a)
    candidates = client.get(f"{API}/departments/{department_a.pk}/head-candidates/").json()
    assert [c["name"] for c in candidates] == ["Asha Rao"] and candidates[0]["designation"]
    ok = _set_head(client, department_a, doctor)
    assert ok.status_code == 200 and ok.json()["head_name"] == "Asha Rao"
    assert _set_head(client, department_a, None).json()["head"] is None


@pytest.mark.django_db
def test_head_is_cleared_when_their_posting_ends(
    client_for, admin_user, organization, department_a
):
    client = client_for(admin_user)
    doctor = _staff(organization)
    posting = _post(doctor, department_a)
    _set_head(client, department_a, doctor)
    yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
    client.post(
        f"{API}/staff/{doctor.pk}/department-assignments/{posting.pk}/end/",
        {"valid_until": yesterday, "reason": "Moved"},
        format="json",
    )
    department_a.refresh_from_db()
    assert department_a.head is None
    event = AuditEvent.objects.filter(action=AuditAction.DEPARTMENT_UPDATED).latest("occurred_at")
    assert event.reason == "The head's posting in this department ended"


@pytest.mark.django_db
def test_head_is_cleared_when_terminated(client_for, admin_user, organization, department_a):
    client = client_for(admin_user)
    doctor = _staff(organization)
    _post(doctor, department_a)
    _set_head(client, department_a, doctor)
    client.patch(
        f"{API}/staff/{doctor.pk}/",
        {"version": 1, "employment_status": "terminated"},
        format="json",
    )
    department_a.refresh_from_db()
    assert department_a.head is None


# --- Opening hours ----------------------------------------------------------------------------


def _hours(client, department, sessions, open_24_hours=False, version=None):
    department.refresh_from_db()
    return client.put(
        f"{API}/departments/{department.pk}/hours/",
        {
            "version": version or department.version,
            "open_24_hours": open_24_hours,
            "sessions": sessions,
        },
        format="json",
    )


@pytest.mark.django_db
def test_weekly_hours_replace_the_timetable_and_are_audited(client_for, admin_user, department_a):
    client = client_for(admin_user)
    week = [
        {"weekday": 0, "opens_at": "09:00", "closes_at": "13:00"},
        {"weekday": 0, "opens_at": "17:00", "closes_at": "20:00"},
        {"weekday": 5, "opens_at": "09:00", "closes_at": "12:00"},
    ]
    saved = _hours(client, department_a, week)
    assert saved.status_code == 200
    body = saved.json()
    assert body["hours"] == week and body["timezone"] == "Asia/Kolkata"
    assert body["open_24_hours"] is False

    again = _hours(client, department_a, [], open_24_hours=True)
    assert again.json()["hours"] == [] and again.json()["open_24_hours"] is True
    event = AuditEvent.objects.filter(action=AuditAction.DEPARTMENT_HOURS_CHANGED).latest(
        "occurred_at"
    )
    assert event.changes["before"]["hours"] == [
        "Monday 09:00-13:00",
        "Monday 17:00-20:00",
        "Saturday 09:00-12:00",
    ]
    assert event.changes["after"] == {"open_24_hours": True, "hours": []}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("sessions", "message"),
    [
        ([{"weekday": 1, "opens_at": "13:00", "closes_at": "09:00"}], "closing time must be after"),
        (
            [
                {"weekday": 2, "opens_at": "09:00", "closes_at": "13:00"},
                {"weekday": 2, "opens_at": "12:00", "closes_at": "15:00"},
            ],
            "sessions overlap",
        ),
        (
            [
                {"weekday": 3, "opens_at": f"{h:02d}:00", "closes_at": f"{h:02d}:30"}
                for h in range(8, 13)
            ],
            "at most 4",
        ),
    ],
)
def test_bad_timetables_are_refused(client_for, admin_user, department_a, sessions, message):
    response = _hours(client_for(admin_user), department_a, sessions)
    assert response.status_code == 400
    assert message in str(response.json())


@pytest.mark.django_db
def test_stale_timetable_is_refused(client_for, admin_user, department_a):
    client = client_for(admin_user)
    _hours(client, department_a, [])
    assert _hours(client, department_a, [], version=1).status_code == 409


# --- Services ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_services_add_rename_switch_off(client_for, admin_user, department_a):
    client = client_for(admin_user)
    url = f"{API}/departments/{department_a.pk}/services/"
    added = client.post(
        url, {"name": "Echocardiography", "description": "Adult echo"}, format="json"
    )
    assert added.status_code == 201
    duplicate = client.post(url, {"name": "echocardiography"}, format="json")
    assert duplicate.status_code == 400  # same name, any letter case
    service_id = added.json()["id"]
    off = client.patch(
        f"{API}/department-services/{service_id}/",
        {"version": 1, "is_active": False},
        format="json",
    )
    assert off.status_code == 200 and off.json()["is_active"] is False
    detail = client.get(f"{API}/departments/{department_a.pk}/").json()
    assert [s["name"] for s in detail["services"]] == ["Echocardiography"]
    assert DepartmentService.objects.count() == 1  # never deleted


@pytest.mark.django_db
def test_other_facility_admins_cannot_change_services(
    client_for, admin_user, make_user, system_roles, department_a, facility_b
):
    service_id = (
        client_for(admin_user)
        .post(f"{API}/departments/{department_a.pk}/services/", {"name": "ECG"}, format="json")
        .json()["id"]
    )
    other = client_for(make_user(role=system_roles["facility-administrator"], facility=facility_b))
    response = other.patch(
        f"{API}/department-services/{service_id}/", {"version": 1, "name": "X"}, format="json"
    )
    assert response.status_code in (403, 404)


@pytest.mark.django_db
def test_admin_console_hours_use_the_same_rules(admin_user, department_a):
    console = Client()
    console.force_login(admin_user)
    form = {
        "name": department_a.name,
        "department_type": "clinical",
        "status": "active",
        "services-TOTAL_FORMS": "0",
        "services-INITIAL_FORMS": "0",
        "hours-TOTAL_FORMS": "2",
        "hours-INITIAL_FORMS": "0",
        "hours-0-weekday": "0",
        "hours-0-opens_at": "09:00",
        "hours-0-closes_at": "13:00",
        "hours-1-weekday": "0",
        "hours-1-opens_at": "12:00",
        "hours-1-closes_at": "14:00",
    }
    url = f"/admin/facilities/department/{department_a.pk}/change/"
    overlapping = console.post(url, form)
    assert overlapping.status_code == 200 and b"sessions overlap" in overlapping.content
    form["hours-1-opens_at"] = "14:00"
    form["hours-1-closes_at"] = "17:00"
    assert console.post(url, form).status_code == 302
    assert department_a.hours.count() == 2
    assert AuditEvent.objects.filter(action=AuditAction.DEPARTMENT_HOURS_CHANGED).exists()


# --- Catalogs (HIMS-STAFF-010) ----------------------------------------------------------------


@pytest.mark.django_db
def test_hr_adds_and_edits_catalog_entries(client_for, make_user, system_roles):
    hr = client_for(make_user(role=system_roles["hr-credentialing-officer"]))
    created = hr.post(
        f"{API}/designations/",
        {
            "name": "Senior Dialysis Technician",
            "category": "allied_health",
            "country": "IN",
            "seniority": 4,
        },
        format="json",
    )
    assert created.status_code == 201, created.json()
    row = created.json()
    assert row["code"] == "in-senior-dialysis-technician" and row["is_custom"] is True
    again = hr.post(
        f"{API}/designations/",
        {
            "name": "senior dialysis technician",
            "category": "allied_health",
            "country": "IN",
            "seniority": 4,
        },
        format="json",
    )
    assert again.json()["code"] == "DUPLICATE_NAME"
    renamed = hr.patch(
        f"{API}/designations/{row['id']}/",
        {"version": 1, "name": "Sr Dialysis Technician"},
        format="json",
    )
    assert renamed.status_code == 200 and renamed.json()["code"] == "in-senior-dialysis-technician"
    assert AuditEvent.objects.filter(action=AuditAction.CATALOG_ITEM_CREATED).count() == 1


@pytest.mark.django_db
def test_switched_off_entries_leave_drop_downs_but_not_the_catalog_screen(client_for, admin_user):
    client = client_for(admin_user)
    specialty = Specialty.objects.get(code="cardiology")
    off = client.patch(
        f"{API}/specialties/{specialty.pk}/", {"version": 1, "is_active": False}, format="json"
    )
    assert off.status_code == 200
    drop_down = {s["code"] for s in client.get(f"{API}/specialties/").json()}
    everything = {
        s["code"] for s in client.get(f"{API}/specialties/", {"include_inactive": "true"}).json()
    }
    assert "cardiology" not in drop_down and "cardiology" in everything
    stale = client.patch(
        f"{API}/specialties/{specialty.pk}/", {"version": 1, "name": "X"}, format="json"
    )
    assert stale.status_code == 409


@pytest.mark.django_db
def test_only_catalog_managers_can_change_catalogs(client_for, make_user, system_roles, facility_a):
    for role, scope in (("basic-staff", None), ("facility-administrator", facility_a)):
        client = client_for(make_user(role=system_roles[role], facility=scope))
        response = client.post(f"{API}/specialties/", {"name": "Sleep medicine"}, format="json")
        assert response.status_code == 403, role


@pytest.mark.django_db
def test_admin_console_catalog_codes_are_locked_and_additions_marked(admin_user):
    console = Client()
    console.force_login(admin_user)
    added = console.post(
        "/admin/staff/specialty/add/",
        {"code": "sleep-medicine", "name": "Sleep medicine", "is_active": "on"},
    )
    assert added.status_code == 302
    specialty = Specialty.objects.get(code="sleep-medicine")
    assert specialty.is_custom is True
    page = console.get(f"/admin/staff/specialty/{specialty.pk}/change/")
    assert b'name="code"' not in page.content  # read-only once created


@pytest.mark.django_db
def test_switched_off_entry_can_be_switched_back_on(client_for, admin_user):
    client = client_for(admin_user)
    specialty = Specialty.objects.get(code="cardiology")
    client.patch(
        f"{API}/specialties/{specialty.pk}/", {"version": 1, "is_active": False}, format="json"
    )
    back = client.patch(
        f"{API}/specialties/{specialty.pk}/", {"version": 2, "is_active": True}, format="json"
    )
    assert back.status_code == 200 and back.json()["is_active"] is True
