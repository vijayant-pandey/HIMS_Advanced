"""What the Staff and Access screens need (HIMS-STAFF-007, HIMS-IAM-013). Synthetic data only."""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.access_control.models import Role
from apps.access_control.services import create_role
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.staff.models import Designation, QualificationType, StaffMember

API = "/api/v1"
NURSE = {
    "email": "nurse.mary@synthetic.test",
    "employee_number": "EMP-0101",
    "given_name": "Mary",
    "family_name": "Joseph",
    "staff_type": "nurse",
    "joined_on": "2026-01-05",
}


@pytest.fixture
def nurse(client_for, admin_user):
    response = client_for(admin_user).post(f"{API}/staff/", NURSE, format="json")
    assert response.status_code == 201, response.json()
    return StaffMember.objects.get(pk=response.json()["id"])


def _assign(client, staff, department, **extra):
    body = {
        "department": str(department.pk),
        "designation": str(Designation.objects.get(code="in-staff-nurse").pk),
        "valid_from": "2026-01-05",
        "is_primary": True,
        **extra,
    }
    response = client.post(f"{API}/staff/{staff.pk}/department-assignments/", body, format="json")
    assert response.status_code == 201, response.json()
    return response.json()


def _qualify(client, staff):
    body = {
        "qualification_type": str(QualificationType.objects.get(code="in-bsc-nursing").pk),
        "institution": "Synthetic College of Nursing",
        "year_awarded": 2020,
    }
    response = client.post(f"{API}/staff/{staff.pk}/qualifications/", body, format="json")
    assert response.status_code == 201, response.json()
    return response.json()


# --- Staff detail -----------------------------------------------------------------------------


@pytest.mark.django_db
def test_detail_shows_names_account_and_expiry(client_for, admin_user, nurse, department_a):
    client = client_for(admin_user)
    _assign(client, nurse, department_a)
    _qualify(client, nurse)
    soon = (timezone.localdate() + timedelta(days=30)).isoformat()
    client.post(
        f"{API}/staff/{nurse.pk}/credentials/",
        {
            "credential_type": "nursing_registration",
            "registration_number": "KNC-55501",
            "issuing_authority": "Karnataka Nursing Council",
            "jurisdiction": "IN-KA",
            "expires_at": soon,
        },
        format="json",
    )
    client.post(f"{API}/staff/{nurse.pk}/invitation/")

    detail = client.get(f"{API}/staff/{nurse.pk}/").json()
    assert detail["staff_type_label"] == "Nurse"
    assert detail["employment_status_label"] == "Active"
    posting = detail["department_assignments"][0]
    assert (posting["department_name"], posting["facility_name"]) == (
        "Cardiology",
        "Facility FAC-A",
    )
    assert posting["designation_name"] and posting["is_current"] is True
    assert detail["qualifications"][0]["qualification_type_name"]
    credential = detail["credentials"][0]
    assert credential["credential_type_label"] == "Nursing council registration"
    assert credential["expiry_state"] == "expiring_soon"
    account = detail["account"]
    assert account["has_login"] and account["is_active"]
    assert account["activated"] is False  # has not chosen a password yet
    assert account["invitation_expires_at"] is not None


@pytest.mark.django_db
def test_list_filters_by_employment_status(client_for, admin_user, nurse):
    client = client_for(admin_user)
    client.patch(
        f"{API}/staff/{nurse.pk}/",
        {"version": 1, "employment_status": "on_leave"},
        format="json",
    )
    assert (
        len(client.get(f"{API}/staff/", {"employment_status": "on_leave"}).json()["results"]) == 1
    )
    assert client.get(f"{API}/staff/", {"employment_status": "active"}).json()["results"] == []


# --- Ending a posting -------------------------------------------------------------------------


@pytest.mark.django_db
def test_end_posting_keeps_history_and_is_audited(client_for, admin_user, nurse, department_a):
    client = client_for(admin_user)
    posting = _assign(client, nurse, department_a)
    url = f"{API}/staff/{nurse.pk}/department-assignments/{posting['id']}/end/"

    too_early = client.post(url, {"valid_until": "2025-12-31", "reason": "x"}, format="json")
    assert too_early.status_code == 409
    assert too_early.json()["code"] == "INVALID_END_DATE"

    yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
    ended = client.post(url, {"valid_until": yesterday, "reason": "Transferred"}, format="json")
    assert ended.status_code == 200
    assert ended.json()["is_current"] is False and ended.json()["is_primary"] is False
    again = client.post(url, {"reason": "again"}, format="json")
    assert again.json()["code"] == "ALREADY_ENDED"
    event = AuditEvent.objects.get(action=AuditAction.STAFF_DEPARTMENT_ASSIGNMENT_ENDED)
    assert event.reason == "Transferred"


@pytest.mark.django_db
def test_cannot_end_another_persons_posting(client_for, admin_user, nurse, department_a):
    client = client_for(admin_user)
    posting = _assign(client, nurse, department_a)
    other = client.post(
        f"{API}/staff/", {**NURSE, "email": None, "employee_number": "EMP-0102"}, format="json"
    ).json()
    url = f"{API}/staff/{other['id']}/department-assignments/{posting['id']}/end/"
    assert client.post(url, {"reason": "x"}, format="json").status_code == 404


# --- Verifying a qualification ----------------------------------------------------------------


@pytest.mark.django_db
def test_verify_qualification_rules(client_for, admin_user, make_user, system_roles, nurse):
    client = client_for(admin_user)
    qualification = _qualify(client, nurse)
    url = f"{API}/staff/{nurse.pk}/qualifications/{qualification['id']}/verify/"

    basic = client_for(make_user(role=system_roles["basic-staff"]))
    assert basic.post(url, {"verified": True}, format="json").status_code == 403

    hr = make_user(role=system_roles["hr-credentialing-officer"])
    ok = client_for(hr).post(url, {"verified": True, "reason": "Saw original"}, format="json")
    assert ok.status_code == 200
    assert ok.json()["verification_status"] == "verified"
    assert ok.json()["verified_by_name"] == hr.display_name
    twice = client_for(hr).post(url, {"verified": False}, format="json")
    assert twice.json()["code"] == "INVALID_STATE_TRANSITION"
    assert AuditEvent.objects.filter(action=AuditAction.STAFF_QUALIFICATION_VERIFIED).count() == 1


@pytest.mark.django_db
def test_nobody_verifies_their_own_qualification(client_for, admin_user, system_roles, nurse):
    from apps.access_control.services import assign_role

    qualification = _qualify(client_for(admin_user), nurse)
    assign_role(actor=None, user=nurse.user, role=system_roles["hr-credentialing-officer"])
    response = client_for(nurse.user).post(
        f"{API}/staff/{nurse.pk}/qualifications/{qualification['id']}/verify/",
        {"verified": True},
        format="json",
    )
    assert response.json()["code"] == "SELF_VERIFICATION"


# --- Roles and access -------------------------------------------------------------------------


@pytest.mark.django_db
def test_custom_role_can_be_edited_with_audit_and_version(client_for, admin_user, organization):
    role = create_role(
        actor=admin_user,
        organization=organization,
        code="ward-clerk-plus",
        name="Ward clerk plus",
        permissions=["locations.view"],
    )
    client = client_for(admin_user)
    url = f"{API}/roles/{role.pk}/"
    body = {
        "version": 1,
        "name": "Senior ward clerk",
        "permissions": ["locations.view", "beds.status.manage"],
    }
    changed = client.patch(url, body, format="json")
    assert changed.status_code == 200
    assert changed.json()["permissions"] == ["beds.status.manage", "locations.view"]
    assert changed.json()["version"] == 2
    assert client.patch(url, body, format="json").status_code == 409  # old copy
    event = AuditEvent.objects.get(action=AuditAction.ROLE_UPDATED)
    assert event.changes["after"]["name"] == "Senior ward clerk"


@pytest.mark.django_db
def test_system_roles_and_escalation_are_refused(
    client_for, admin_user, organization, system_roles
):
    client = client_for(admin_user)
    system = system_roles["basic-staff"]
    refused = client.patch(f"{API}/roles/{system.pk}/", {"version": 1, "name": "X"}, format="json")
    assert refused.json()["code"] == "SYSTEM_ROLE_READ_ONLY"

    role = create_role(
        actor=None,
        organization=organization,
        code="custom",
        name="Custom",
        permissions=["staff.view"],
    )
    # The administrator does not hold audit.view (separation of duties), so cannot hand it out.
    escalate = client.patch(
        f"{API}/roles/{role.pk}/",
        {"version": 1, "permissions": ["staff.view", "audit.view"]},
        format="json",
    )
    assert escalate.status_code == 403
    assert sorted(Role.objects.get(pk=role.pk).permissions.values_list("codename", flat=True)) == [
        "staff.view"
    ]


@pytest.mark.django_db
def test_assignment_list_has_names_counts_and_filters(
    client_for, admin_user, make_user, system_roles, facility_a
):
    nurse_user = make_user(display_name="Synthetic Nurse")
    client = client_for(admin_user)
    granted = client.post(
        f"{API}/role-assignments/",
        {
            "user": str(nurse_user.pk),
            "role": str(system_roles["basic-staff"].pk),
            "facility": str(facility_a.pk),
            "reason": "New joiner",
        },
        format="json",
    ).json()
    assert granted["role_name"] == "Basic staff access"
    assert granted["user_display_name"] == "Synthetic Nurse"
    assert granted["facility_name"] == "Facility FAC-A"
    assert granted["granted_by_name"] == admin_user.display_name
    assert granted["is_active"] is True

    client.post(
        f"{API}/role-assignments/{granted['id']}/revoke/", {"reason": "Left"}, format="json"
    )
    active = client.get(
        f"{API}/role-assignments/", {"user": str(nurse_user.pk), "active": "true"}
    ).json()["results"]
    assert active == []
    every = client.get(f"{API}/role-assignments/", {"role": str(system_roles["basic-staff"].pk)})
    revoked = next(r for r in every.json()["results"] if r["id"] == granted["id"])
    assert revoked["is_active"] is False and revoked["revoked_by_name"] == admin_user.display_name

    roles = {r["code"]: r for r in client.get(f"{API}/roles/").json()["results"]}
    assert roles["organization-administrator"]["active_assignments"] == 1


@pytest.mark.django_db
def test_current_user_includes_hospital_name_and_country(client_for, admin_user):
    me = client_for(admin_user).get(f"{API}/auth/me/").json()
    assert me["organization"] == {"display_name": "Synthetic Health", "country": "IN"}


@pytest.mark.django_db
def test_expired_credential_state(client_for, admin_user, nurse):
    client = client_for(admin_user)
    client.post(
        f"{API}/staff/{nurse.pk}/credentials/",
        {
            "credential_type": "nursing_registration",
            "registration_number": "KNC-55502",
            "issuing_authority": "Karnataka Nursing Council",
            "jurisdiction": "IN-KA",
            "valid_from": "2020-01-01",
            "expires_at": (date.today() - timedelta(days=1)).isoformat(),
        },
        format="json",
    )
    detail = client.get(f"{API}/staff/{nurse.pk}/").json()
    assert detail["credentials"][0]["expiry_state"] == "expired"


@pytest.mark.django_db
def test_nobody_can_give_themselves_access(client_for, admin_user, system_roles):
    response = client_for(admin_user).post(
        f"{API}/role-assignments/",
        {"user": str(admin_user.pk), "role": str(system_roles["basic-staff"].pk), "reason": "x"},
        format="json",
    )
    assert response.status_code == 409
    assert response.json()["code"] == "SELF_ASSIGNMENT"
