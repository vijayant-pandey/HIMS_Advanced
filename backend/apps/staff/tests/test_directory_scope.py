"""Staff list limited to your own departments (HIMS-STAFF-008; spec 4.4, 13.2). Synthetic data."""

import importlib
from datetime import date, timedelta

import pytest
from django.apps import apps as django_apps
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.access_control.models import Permission, RolePermission
from apps.access_control.services import create_role
from apps.facilities.models import Department
from apps.organizations.dates import hospital_today
from apps.staff.models import Designation, StaffCredential, StaffDepartmentAssignment, StaffMember

API = "/api/v1"
PDF = b"%PDF-1.4\n% synthetic test document\n%%EOF\n"
_n = iter(range(1, 10_000))


@pytest.fixture
def client_for(client_for):
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
def department_c(facility_b):
    return Department.objects.create(
        organization_id=facility_b.organization_id,
        facility=facility_b,
        code="peds",
        name="Paediatrics",
        department_type=Department.DepartmentType.CLINICAL,
    )


@pytest.fixture
def staff(organization):
    """A staff member, posted in the given department (or nowhere)."""

    def factory(name, department=None, *, starts=None, ends=None):
        n = next(_n)
        person = StaffMember.objects.create(
            organization=organization,
            employee_number=f"EMP-DIR-{n}",
            given_name=name,
            family_name=f"Dir{n}",
            staff_type="nurse",
            joined_on="2026-01-05",
        )
        if department is not None:
            StaffDepartmentAssignment.objects.create(
                organization=organization,
                staff=person,
                department=department,
                designation=Designation.objects.first(),
                valid_from=starts or hospital_today() - timedelta(days=30),
                valid_until=ends,
            )
        return person

    return factory


@pytest.fixture
def head(make_user, system_roles, department_a):
    return make_user(
        role=system_roles["department-head"],
        facility=department_a.facility,
        department=department_a,
    )


@pytest.fixture
def hr(make_user, system_roles):
    return make_user(role=system_roles["hr-credentialing-officer"])


def names(response) -> set[str]:
    assert response.status_code == 200, response.json()
    return {row["given_name"] for row in response.json()["results"]}


@pytest.mark.django_db
def test_head_sees_only_staff_posted_in_their_department(
    client_for, head, staff, department_a, department_b
):
    staff("Asha", department_a)
    staff("Future", department_a, starts=hospital_today() + timedelta(days=10))
    staff("Moved", department_a, ends=hospital_today() - timedelta(days=1))
    staff("Ravi", department_b)
    staff("Unposted")
    client = client_for(head)
    assert names(client.get(f"{API}/staff/")) == {"Asha", "Future"}
    assert names(client.get(f"{API}/staff/", {"search": "Ravi"})) == set()


@pytest.mark.django_db
def test_facility_grant_sees_the_whole_facility_only(
    client_for, make_user, system_roles, staff, department_a, department_b, department_c
):
    branch_admin = make_user(
        role=system_roles["facility-administrator"], facility=department_a.facility
    )
    staff("Asha", department_a)
    staff("Ravi", department_b)
    staff("Meena", department_c)
    assert names(client_for(branch_admin).get(f"{API}/staff/")) == {"Asha", "Ravi"}


@pytest.mark.django_db
def test_hospital_wide_grant_sees_everyone(client_for, hr, staff, department_a, department_c):
    staff("Asha", department_a)
    staff("Meena", department_c)
    staff("Unposted")
    assert names(client_for(hr).get(f"{API}/staff/")) == {"Asha", "Meena", "Unposted"}


@pytest.mark.django_db
def test_someone_elsewhere_is_not_found_and_changes_stay_hospital_wide(
    client_for, head, staff, department_a, department_b
):
    mine, other = staff("Asha", department_a), staff("Ravi", department_b)
    client = client_for(head)
    detail = client.get(f"{API}/staff/{mine.pk}/")
    assert detail.status_code == 200 and detail.json()["given_name"] == "Asha"
    assert client.get(f"{API}/staff/{other.pk}/").status_code == 404
    edit = client.patch(f"{API}/staff/{mine.pk}/", {"version": mine.version, "given_name": "X"})
    assert edit.status_code == 403
    new = {
        "employee_number": "E-1",
        "given_name": "New",
        "family_name": "Person",
        "staff_type": "nurse",
        "joined_on": "2026-01-05",
    }
    assert client.post(f"{API}/staff/", new).status_code == 403


@pytest.mark.django_db
def test_seeing_a_person_does_not_open_their_documents(
    client_for, admin_user, head, hr, staff, department_a
):
    asha = staff("Asha", department_a)
    licence = StaffCredential.objects.create(
        organization_id=asha.organization_id,
        staff=asha,
        credential_type="nursing_registration",
        registration_number="KNC-DIR-1",
        issuing_authority="Karnataka Nursing Council",
        jurisdiction="IN-KA",
        expires_at=date(2027, 1, 1),
    )
    upload = client_for(admin_user).post(
        f"{API}/staff/{asha.pk}/documents/",
        {"file": SimpleUploadedFile("licence.pdf", PDF), "credential": str(licence.pk)},
        format="multipart",
    )
    assert upload.status_code == 201, upload.json()
    document = upload.json()["id"]

    by_head = client_for(head).get(f"{API}/staff/{asha.pk}/").json()
    assert by_head["documents_visible"] is False and by_head["documents"] == []
    assert by_head["credentials"][0]["registration_number"] == "KNC-DIR-1"  # the licence itself
    assert client_for(head).get(f"{API}/staff/{asha.pk}/documents/").status_code == 403
    assert client_for(head).get(f"{API}/staff-documents/{document}/download/").status_code == 403

    by_hr = client_for(hr).get(f"{API}/staff/{asha.pk}/").json()
    assert by_hr["documents_visible"] is True and len(by_hr["documents"]) == 1
    assert client_for(hr).get(f"{API}/staff-documents/{document}/download/").status_code == 200


@pytest.mark.django_db
def test_licence_expiry_list_follows_the_same_scope(
    client_for, head, hr, staff, department_a, department_b
):
    for name, department in (("Asha", department_a), ("Ravi", department_b)):
        StaffCredential.objects.create(
            organization_id=department.organization_id,
            staff=staff(name, department),
            credential_type="nursing_registration",
            registration_number=f"KNC-{name}",
            issuing_authority="Karnataka Nursing Council",
            jurisdiction="IN-KA",
            expires_at=hospital_today() + timedelta(days=20),
        )
    url = f"{API}/staff-credentials/expiring/"
    assert [r["registration_number"] for r in client_for(head).get(url).json()] == ["KNC-Asha"]
    assert len(client_for(hr).get(url).json()) == 2


@pytest.mark.django_db
def test_catalogs_are_readable_with_a_department_grant_but_not_changeable(client_for, head):
    client = client_for(head)
    assert client.get(f"{API}/designations/").status_code == 200
    body = {"code": "x-ray-lead", "name": "X-ray lead", "category": "allied", "seniority": 3}
    assert client.post(f"{API}/designations/", body).status_code == 403


@pytest.mark.django_db
def test_roles_that_could_open_documents_keep_that_access(organization, system_roles):
    """The data migration: every role with staff.view also gets staff.documents.view."""
    custom = create_role(
        actor=None,
        organization=organization,
        code="ward-clerk-plus",
        name="Ward clerk plus",
        permissions=["staff.view"],
    )
    RolePermission.objects.filter(permission__codename="staff.documents.view").delete()
    migration = importlib.import_module(
        "apps.access_control.migrations.0005_staff_documents_permission"
    )
    migration.keep_document_access(django_apps, None)
    with_documents = set(
        RolePermission.objects.filter(permission__codename="staff.documents.view").values_list(
            "role__code", flat=True
        )
    )
    assert {"ward-clerk-plus", "organization-administrator", "hr-credentialing-officer"} <= (
        with_documents
    )
    assert Permission.objects.get(codename="staff.documents.view").is_active
    assert custom.pk


@pytest.mark.django_db
def test_head_of_department_role_sees_staff_but_not_documents(system_roles):
    head = set(system_roles["department-head"].permissions.values_list("codename", flat=True))
    hr = set(
        system_roles["hr-credentialing-officer"].permissions.values_list("codename", flat=True)
    )
    assert "staff.view" in head and "staff.documents.view" not in head
    assert "staff.documents.view" in hr
