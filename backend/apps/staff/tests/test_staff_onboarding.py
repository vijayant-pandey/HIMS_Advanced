"""Vertical slice steps 3-4 (spec 21): onboard a doctor with qualifications, credentials and
department-limited access."""

import pytest

from apps.access_control.catalog import P
from apps.access_control.services import create_role
from apps.identity.models import User
from apps.staff.models import (
    Designation,
    QualificationType,
    Specialty,
    StaffCredential,
    StaffMember,
)
from common.outbox.models import OutboxEvent

DOCTOR = {
    "email": "dr.rao@synthetic.test",
    "employee_number": "EMP-0001",
    "given_name": "Asha",
    "family_name": "Rao",
    "staff_type": "doctor",
    "joined_on": "2026-01-05",
}


@pytest.fixture
def doctor(client_for, admin_user):
    response = client_for(admin_user).post("/api/v1/staff/", DOCTOR, format="json")
    assert response.status_code == 201, response.json()
    return StaffMember.objects.get(pk=response.json()["id"])


@pytest.mark.django_db
def test_onboard_doctor_end_to_end(client_for, admin_user, doctor, department_a, organization):
    client = client_for(admin_user)
    base = f"/api/v1/staff/{doctor.pk}"

    assert doctor.user.email == "dr.rao@synthetic.test"
    assert not doctor.user.has_usable_password()  # waits for the invitation flow
    assert OutboxEvent.objects.filter(
        event_type="staff.member.created", aggregate_id=str(doctor.pk)
    ).exists()

    cardiology = Specialty.objects.get(code="cardiology")
    qualification = client.post(
        f"{base}/qualifications/",
        {
            "qualification_type": str(QualificationType.objects.get(code="in-md").pk),
            "specialty": str(cardiology.pk),
            "institution": "Synthetic Medical College",
            "year_awarded": 2015,
        },
        format="json",
    )
    assert qualification.status_code == 201
    assert qualification.json()["verification_status"] == "unverified"

    credential = client.post(
        f"{base}/credentials/",
        {
            "credential_type": "medical_registration",
            "registration_number": "KMC-000123",
            "issuing_authority": "Karnataka Medical Council",
            "jurisdiction": "IN-KA",
            "valid_from": "2015-06-01",
            "expires_at": "2030-06-01",
        },
        format="json",
    )
    assert credential.status_code == 201

    assignment = client.post(
        f"{base}/department-assignments/",
        {
            "department": str(department_a.pk),
            "designation": str(Designation.objects.get(code="in-consultant").pk),
            "specialty": str(cardiology.pk),
            "is_primary": True,
            "valid_from": "2026-01-05",
        },
        format="json",
    )
    assert assignment.status_code == 201

    detail = client.get(f"{base}/").json()
    assert len(detail["qualifications"]) == 1
    assert len(detail["credentials"]) == 1
    assert detail["department_assignments"][0]["designation_name"] == "Consultant"

    # Step 4: access limited to the authorized hospital department.
    role = create_role(
        actor=None,
        organization=organization,
        code="consultant",
        name="Consultant",
        permissions=[P.DEPARTMENTS_VIEW],
    )
    grant = client.post(
        "/api/v1/role-assignments/",
        {
            "user": str(doctor.user.pk),
            "role": str(role.pk),
            "facility": str(department_a.facility_id),
            "department": str(department_a.pk),
            "reason": "Cardiology consultant",
        },
        format="json",
    )
    assert grant.status_code == 201
    doctor_client = client_for(doctor.user)
    visible = doctor_client.get("/api/v1/departments/").json()["results"]
    assert [d["id"] for d in visible] == [str(department_a.pk)]
    assert doctor_client.get("/api/v1/staff/").status_code == 403


@pytest.mark.django_db
def test_duplicate_credential_is_conflict(client_for, admin_user, doctor):
    payload = {
        "credential_type": "medical_registration",
        "registration_number": "KMC-1",
        "issuing_authority": "Karnataka Medical Council",
        "jurisdiction": "IN-KA",
    }
    client = client_for(admin_user)
    assert (
        client.post(f"/api/v1/staff/{doctor.pk}/credentials/", payload, format="json").status_code
        == 201
    )
    again = client.post(f"/api/v1/staff/{doctor.pk}/credentials/", payload, format="json")
    assert again.status_code == 409


@pytest.mark.django_db
def test_credential_cannot_be_self_verified(client_for, organization, system_roles, make_user):
    verifier_role = create_role(
        actor=None,
        organization=organization,
        code="credentialing",
        name="Credentialing officer",
        permissions=[P.STAFF_CREDENTIALS_VERIFY],
    )
    user = make_user(role=verifier_role)
    staff = StaffMember.objects.create(
        organization=organization,
        user=user,
        employee_number="EMP-9",
        given_name="Self",
        family_name="Verifier",
        staff_type="doctor",
        joined_on="2026-01-01",
    )
    credential = StaffCredential.objects.create(
        organization=organization,
        staff=staff,
        credential_type="medical_registration",
        registration_number="X-1",
        issuing_authority="Council",
        jurisdiction="IN-KA",
    )
    response = client_for(user).post(
        f"/api/v1/staff-credentials/{credential.pk}/verify/", {"verified": True}, format="json"
    )
    assert response.status_code == 409
    assert response.json()["code"] == "SELF_VERIFICATION"


@pytest.mark.django_db
def test_terminating_staff_disables_login_and_access(client_for, admin_user, doctor):
    response = client_for(admin_user).patch(
        f"/api/v1/staff/{doctor.pk}/",
        {"version": 1, "employment_status": "terminated", "left_on": "2026-06-30"},
        format="json",
    )
    assert response.status_code == 200
    assert not User.objects.get(pk=doctor.user_id).is_active
    assert OutboxEvent.objects.filter(event_type="staff.member.employment_status_changed").exists()


@pytest.mark.django_db
def test_left_on_before_joined_on_is_rejected(client_for, admin_user, doctor):
    response = client_for(admin_user).patch(
        f"/api/v1/staff/{doctor.pk}/", {"version": 1, "left_on": "2020-01-01"}, format="json"
    )
    assert response.status_code == 400
