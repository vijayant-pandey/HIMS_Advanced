"""Designation catalog and administrative system roles (HIMS-STAFF-009)."""

import pytest
from django.db import IntegrityError

from apps.access_control.models import Role
from apps.access_control.services import assign_role, sync_system_roles
from apps.staff.models import Designation, StaffCredential, StaffMember

EXPECTED_SYSTEM_ROLES = {
    "organization-administrator",
    "auditor",
    "facility-administrator",
    "hr-credentialing-officer",
    "department-head",
    "basic-staff",
}


@pytest.mark.django_db
def test_catalog_has_junior_to_senior_ladders_for_india_and_us():
    india_doctors = list(
        Designation.objects.filter(category="medical", country="IN").values_list("code", flat=True)
    )
    assert india_doctors[0] == "in-intern"  # ordered by seniority
    assert india_doctors[-1] == "in-medical-director"
    us = set(Designation.objects.filter(country="US").values_list("code", flat=True))
    assert {"us-intern", "us-resident", "us-attending-physician", "us-registered-nurse"} <= us
    assert Designation.objects.filter(code="in-ot-technician", category="allied_health").exists()


@pytest.mark.django_db
def test_seniority_must_be_between_1_and_10():
    with pytest.raises(IntegrityError):
        Designation.objects.create(code="x", name="X", category="other", seniority=11)


@pytest.mark.django_db
def test_designation_list_filters_by_country(client_for, admin_user):
    response = client_for(admin_user).get("/api/v1/designations/", {"country": "US"})
    assert response.status_code == 200
    countries = {row["country"] for row in response.json()}
    assert countries == {"US", ""}  # US titles plus titles used in both countries


@pytest.mark.django_db
def test_assignment_rejects_free_text_designation(client_for, admin_user, department_a):
    staff = StaffMember.objects.create(
        organization=department_a.facility.organization,
        employee_number="EMP-D1",
        given_name="A",
        family_name="B",
        staff_type="doctor",
        joined_on="2026-01-01",
    )
    response = client_for(admin_user).post(
        f"/api/v1/staff/{staff.pk}/department-assignments/",
        {
            "department": str(department_a.pk),
            "designation": "Consultant",
            "valid_from": "2026-01-01",
        },
        format="json",
    )
    assert response.status_code == 400
    assert {e["field"] for e in response.json()["errors"]} == {"designation"}


@pytest.mark.django_db
def test_system_roles_exist_and_are_added_to_existing_hospitals(organization, system_roles):
    assert set(system_roles) == EXPECTED_SYSTEM_ROLES
    Role.objects.filter(code="basic-staff").delete()  # simulate a hospital provisioned earlier
    sync_system_roles()  # runs after every migrate
    assert Role.objects.get(code="basic-staff").is_system


@pytest.mark.django_db
def test_hr_officer_can_onboard_and_verify_but_not_change_facilities(
    client_for, make_user, system_roles, organization, facility_a
):
    hr = make_user(role=system_roles["hr-credentialing-officer"])
    client = client_for(hr)
    staff = client.post(
        "/api/v1/staff/",
        {
            "employee_number": "EMP-HR1",
            "given_name": "Kiran",
            "family_name": "Das",
            "staff_type": "nurse",
            "joined_on": "2026-01-01",
        },
        format="json",
    )
    assert staff.status_code == 201
    credential = StaffCredential.objects.create(
        organization=organization,
        staff_id=staff.json()["id"],
        credential_type="nursing_registration",
        registration_number="KNC-1",
        issuing_authority="Karnataka Nursing Council",
        jurisdiction="IN-KA",
    )
    verify = client.post(
        f"/api/v1/staff-credentials/{credential.pk}/verify/", {"verified": True}, format="json"
    )
    assert verify.status_code == 200
    edit_facility = client.patch(
        f"/api/v1/facilities/{facility_a.pk}/", {"version": 1}, format="json"
    )
    assert edit_facility.status_code == 403  # HR holds no facility-management permission


@pytest.mark.django_db
def test_department_head_sees_only_their_department(
    client_for, make_user, system_roles, department_a, facility_b
):
    from apps.facilities.models import Department

    Department.objects.create(
        organization_id=facility_b.organization_id,
        facility=facility_b,
        code="ortho",
        name="Orthopedics",
        department_type="clinical",
    )
    hod = make_user()
    assign_role(
        actor=None,
        user=hod,
        role=system_roles["department-head"],
        facility=department_a.facility,
        department=department_a,
    )
    rows = client_for(hod).get("/api/v1/departments/").json()["results"]
    assert [row["id"] for row in rows] == [str(department_a.pk)]


@pytest.mark.django_db
def test_basic_staff_no_longer_sees_permission_denied(client_for, make_user, system_roles):
    user = make_user(role=system_roles["basic-staff"])
    assert client_for(user).get("/api/v1/facilities/").status_code == 200
