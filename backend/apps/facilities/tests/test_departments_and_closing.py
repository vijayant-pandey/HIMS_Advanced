"""Departments screen and closing rules (HIMS-FAC-006). All data is synthetic."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.access_control.services import assign_role
from apps.facilities.models import Building, Department, Floor, Ward
from apps.staff.models import Designation, StaffDepartmentAssignment, StaffMember

API = "/api/v1"


def _staff(organization, number="EMP-9001"):
    return StaffMember.objects.create(
        organization=organization,
        employee_number=number,
        given_name="Synthetic",
        family_name="Nurse",
        staff_type="nurse",
        joined_on="2026-01-05",
    )


def _post(staff, department, valid_until=None):
    return StaffDepartmentAssignment.objects.create(
        organization_id=staff.organization_id,
        staff=staff,
        department=department,
        designation=Designation.objects.filter(is_active=True).first(),
        valid_from="2026-01-05",
        valid_until=valid_until,
    )


def deactivate(client, department):
    department.refresh_from_db()
    return client.patch(
        f"{API}/departments/{department.pk}/",
        {"version": department.version, "status": "inactive"},
        format="json",
    )


@pytest.mark.django_db
def test_department_with_current_staff_cannot_be_closed(
    client_for, admin_user, organization, department_a
):
    client = client_for(admin_user)
    posting = _post(_staff(organization), department_a)
    refused = deactivate(client, department_a)
    assert refused.status_code == 400
    message = refused.json()["errors"][0]
    assert message["field"] == "status"
    assert "1 staff member is posted here" in message["message"]

    posting.valid_until = timezone.localdate() - timedelta(days=1)  # posting ended yesterday
    posting.save()
    assert deactivate(client, department_a).status_code == 200


@pytest.mark.django_db
def test_department_with_access_or_wards_cannot_be_closed(
    client_for, admin_user, make_user, system_roles, department_a, facility_a
):
    client = client_for(admin_user)
    holder = make_user()
    assignment = assign_role(
        actor=None, user=holder, role=system_roles["department-head"], department=department_a
    )
    building = Building.objects.create(facility=facility_a, code="main", name="Main")
    floor = Floor.objects.create(building=building, level=0, name="Ground")
    ward = Ward.objects.create(
        floor=floor, code="w1", name="Ward 1", ward_type="general", department=department_a
    )
    message = deactivate(client, department_a).json()["errors"][0]["message"]
    assert "1 person has access limited to this department" in message
    assert "1 active ward belongs to it" in message

    assignment.revoked_at = timezone.now()
    assignment.save()
    ward.is_active = False
    ward.save()
    assert deactivate(client, department_a).status_code == 200


@pytest.mark.django_db
def test_department_cannot_be_reactivated_under_inactive_facility(
    client_for, admin_user, department_a, facility_a
):
    client = client_for(admin_user)
    assert deactivate(client, department_a).status_code == 200
    facility_a.refresh_from_db()
    facility_off = client.patch(
        f"{API}/facilities/{facility_a.pk}/",
        {"version": facility_a.version, "status": "inactive"},
        format="json",
    )
    assert facility_off.status_code == 200
    department_a.refresh_from_db()
    back = client.patch(
        f"{API}/departments/{department_a.pk}/",
        {"version": department_a.version, "status": "active"},
        format="json",
    )
    assert back.status_code == 400
    assert back.json()["errors"][0]["message"] == "Reactivate the facility first."


@pytest.mark.django_db
def test_facility_with_active_departments_or_buildings_cannot_be_closed(
    client_for, admin_user, facility_a, department_a
):
    client = client_for(admin_user)
    Building.objects.create(facility=facility_a, code="main", name="Main")
    refused = client.patch(
        f"{API}/facilities/{facility_a.pk}/", {"version": 1, "status": "inactive"}, format="json"
    )
    assert refused.status_code == 400
    message = refused.json()["errors"][0]["message"]
    assert "1 department is still active" in message
    assert "1 building is still active" in message


@pytest.mark.django_db
def test_admin_console_applies_the_same_rule(admin_user, organization, department_a):
    _post(_staff(organization), department_a)
    console = Client()
    console.force_login(admin_user)
    response = console.post(
        f"/admin/facilities/department/{department_a.pk}/change/",
        {
            "facility": str(department_a.facility_id),
            "code": department_a.code,
            "name": department_a.name,
            "department_type": department_a.department_type,
            "status": "inactive",
        },
    )
    assert response.status_code == 200  # form shown again with the message
    assert b"staff member is posted here" in response.content
    department_a.refresh_from_db()
    assert department_a.status == "active"


@pytest.mark.django_db
def test_lists_show_counts_names_and_filter(
    client_for, admin_user, organization, department_a, facility_a
):
    client = client_for(admin_user)
    _post(_staff(organization, "EMP-1"), department_a)
    _post(_staff(organization, "EMP-2"), department_a, valid_until="2026-01-31")  # ended
    row = client.get(f"{API}/departments/", {"facility": str(facility_a.pk)}).json()["results"][0]
    assert row["facility_name"] == "Facility FAC-A"
    assert row["department_type_label"] == "Clinical"
    assert (row["current_staff"], row["active_wards"]) == (1, 0)
    assert client.get(f"{API}/departments/", {"status": "inactive"}).json()["results"] == []

    facility = client.get(f"{API}/facilities/").json()["results"][0]
    assert facility["active_departments"] == 1
    assert facility["facility_type_label"] == "Hospital"

    staff = client.get(f"{API}/staff/", {"department": str(department_a.pk)}).json()["results"]
    assert [s["employee_number"] for s in staff] == ["EMP-1"]


@pytest.mark.django_db
def test_department_edit_and_duplicate_code(client_for, admin_user, department_a, facility_a):
    client = client_for(admin_user)
    edited = client.patch(
        f"{API}/departments/{department_a.pk}/",
        {"version": 1, "name": "Cardiology & Vascular", "department_type": "clinical"},
        format="json",
    )
    assert edited.status_code == 200
    assert edited.json()["current_staff"] == 0  # counts present on single responses too
    duplicate = client.post(
        f"{API}/departments/",
        {
            "facility": str(facility_a.pk),
            "code": "cardio",
            "name": "X",
            "department_type": "clinical",
        },
        format="json",
    )
    assert duplicate.status_code == 409
    assert Department.objects.filter(facility=facility_a).count() == 1
