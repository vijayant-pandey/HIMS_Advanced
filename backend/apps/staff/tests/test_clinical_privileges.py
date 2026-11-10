"""Clinical privileges (HIMS-STAFF-016; spec 4.3). All data is synthetic."""

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.identity import confirmation
from apps.organizations.dates import hospital_today
from apps.staff.models import (
    ClinicalPrivilege,
    Designation,
    StaffDepartmentAssignment,
    StaffMember,
    StaffPrivilege,
)
from apps.staff.privileges import holds_privilege
from apps.staff.services import update_staff_member
from common.admin.tests.test_console_additions import console

API = "/api/v1"
_n = iter(range(1, 10_000))


@pytest.fixture
def client(client_for, admin_user):
    return client_for(admin_user)


@pytest.fixture
def privilege(db):
    return ClinicalPrivilege.objects.create(code="central-line", name="Central line insertion")


@pytest.fixture
def doctor(organization, department_a):
    n = next(_n)
    staff = StaffMember.objects.create(
        organization=organization,
        employee_number=f"EMP-PRIV-{n}",
        given_name="Asha",
        family_name=f"Priv{n}",
        staff_type="doctor",
        joined_on="2026-01-05",
    )
    StaffDepartmentAssignment.objects.create(
        organization=organization,
        staff=staff,
        department=department_a,
        designation=Designation.objects.first(),
        valid_from="2026-01-05",
        is_primary=True,
    )
    return staff


def _grant(client, staff, privilege, **extra):
    body = {"privilege": str(privilege.pk), **extra}
    return client.post(f"{API}/staff/{staff.pk}/privileges/", body, format="json")


@pytest.mark.django_db
def test_hims_ships_no_privileges_the_hospital_writes_the_list(client):
    assert not ClinicalPrivilege.objects.exists()
    added = client.post(
        f"{API}/clinical-privileges/",
        {"name": "Central line insertion", "description": "Adults only"},
        format="json",
    )
    assert added.status_code == 201, added.content
    body = added.json()
    assert body["code"] == "central-line-insertion" and body["is_custom"] is True
    assert body["description"] == "Adults only"
    changed = client.patch(
        f"{API}/clinical-privileges/{body['id']}/",
        {"version": body["version"], "is_active": False},
        format="json",
    )
    assert changed.json()["is_active"] is False
    assert client.get(f"{API}/clinical-privileges/").json() == []  # gone from drop-downs
    assert len(client.get(f"{API}/clinical-privileges/?include_inactive=true").json()) == 1


@pytest.mark.django_db
def test_grant_shows_on_the_person_and_is_audited(client, doctor, privilege, department_a):
    response = _grant(
        client, doctor, privilege, department=str(department_a.pk), note="After supervision"
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["privilege_name"] == "Central line insertion"
    assert body["is_current"] is True and body["granted_by_name"]
    assert body["valid_from"] == hospital_today().isoformat()
    shown = client.get(f"{API}/staff/{doctor.pk}/").json()["privileges"]
    assert [row["id"] for row in shown] == [body["id"]]
    event = AuditEvent.objects.get(action=AuditAction.STAFF_PRIVILEGE_GRANTED)
    assert event.metadata["privilege"] == "central-line"


@pytest.mark.django_db
def test_a_person_cannot_hold_the_same_privilege_twice_at_once(client, doctor, privilege):
    assert _grant(client, doctor, privilege).status_code == 201
    second = _grant(client, doctor, privilege)
    assert second.status_code == 409 and second.json()["code"] == "ALREADY_HELD"
    # The database also refuses it, for two people granting at the same moment.
    with pytest.raises(IntegrityError), transaction.atomic():
        StaffPrivilege.objects.create(
            organization_id=doctor.organization_id,
            staff=doctor,
            privilege=privilege,
            valid_from=hospital_today(),
        )


@pytest.mark.django_db
def test_ending_keeps_the_record_and_allows_a_new_grant(client, doctor, privilege):
    grant = _grant(client, doctor, privilege).json()
    url = f"{API}/staff-privileges/{grant['id']}/end/"
    refused = client.post(url, {"version": grant["version"], "reason": " "}, format="json")
    assert refused.status_code == 400
    ended = client.post(
        url, {"version": grant["version"], "reason": "Moved to teaching"}, format="json"
    )
    assert ended.status_code == 200, ended.content
    body = ended.json()
    assert (body["status"], body["is_current"], body["end_reason"]) == (
        "ended",
        False,
        "Moved to teaching",
    )
    again = client.post(url, {"version": body["version"], "reason": "Twice"}, format="json")
    assert again.status_code == 409
    assert _grant(client, doctor, privilege).status_code == 201
    assert StaffPrivilege.objects.filter(staff=doctor).count() == 2
    assert AuditEvent.objects.filter(action=AuditAction.STAFF_PRIVILEGE_ENDED).count() == 1


@pytest.mark.django_db
def test_nobody_gives_themselves_a_privilege(client_for, admin_user, doctor, privilege):
    StaffMember.objects.filter(pk=doctor.pk).update(user=admin_user)
    doctor.refresh_from_db()
    response = _grant(client_for(admin_user), doctor, privilege)
    assert response.status_code == 409 and response.json()["code"] == "SELF_GRANT"


@pytest.mark.django_db
def test_the_rules_for_a_grant(client, doctor, privilege, department_a, facility_a):
    today = hospital_today()
    earlier = (today - timedelta(days=1)).isoformat()
    assert _grant(client, doctor, privilege, valid_until=earlier).json()["code"] == "INVALID_DATES"
    ClinicalPrivilege.objects.filter(pk=privilege.pk).update(is_active=False)
    assert _grant(client, doctor, privilege).json()["code"] == "PRIVILEGE_OFF"
    ClinicalPrivilege.objects.filter(pk=privilege.pk).update(is_active=True)
    other = department_a.__class__.objects.create(
        organization_id=facility_a.organization_id,
        facility=facility_a,
        code="ortho",
        name="Orthopaedics",
        department_type="clinical",
    )
    assert (
        _grant(client, doctor, privilege, department=str(other.pk)).json()["code"] == "NOT_POSTED"
    )
    StaffMember.objects.filter(pk=doctor.pk).update(employment_status="terminated")
    assert _grant(client, doctor, privilege).json()["code"] == "NOT_WORKING"


@pytest.mark.django_db
def test_holds_privilege_follows_dates_place_and_employment(
    client, doctor, privilege, department_a, facility_a
):
    today = hospital_today()
    assert holds_privilege(doctor, privilege.code) is False
    grant = _grant(
        client,
        doctor,
        privilege,
        department=str(department_a.pk),
        valid_until=(today + timedelta(days=10)).isoformat(),
    ).json()
    assert holds_privilege(doctor, privilege.code, department=department_a) is True
    other = department_a.__class__.objects.create(
        organization_id=facility_a.organization_id,
        facility=facility_a,
        code="ortho",
        name="Orthopaedics",
        department_type="clinical",
    )
    assert holds_privilege(doctor, privilege.code, department=other) is False
    later = today + timedelta(days=11)
    assert holds_privilege(doctor, privilege.code, department=department_a, on_date=later) is False
    assert holds_privilege(doctor, "something-else") is False
    # Past days still answer from the record once it has ended, by the dates it held.
    StaffMember.objects.filter(pk=doctor.pk).update(employment_status="suspended")
    doctor.refresh_from_db()
    assert holds_privilege(doctor, privilege.code, department=department_a) is False
    StaffMember.objects.filter(pk=doctor.pk).update(employment_status="active")
    doctor.refresh_from_db()
    client.post(
        f"{API}/staff-privileges/{grant['id']}/end/",
        {"version": grant["version"], "reason": "Done"},
        format="json",
    )
    assert holds_privilege(doctor, privilege.code, department=department_a) is False


@pytest.mark.django_db
def test_termination_ends_what_the_person_held(client, admin_user, doctor, privilege):
    _grant(client, doctor, privilege)
    update_staff_member(
        actor=admin_user,
        staff_id=doctor.pk,
        version=doctor.version,
        employment_status="terminated",
        left_on=hospital_today(),
    )
    grant = StaffPrivilege.objects.get(staff=doctor)
    assert (grant.status, grant.end_reason) == ("ended", "Employment ended")
    assert grant.ended_by is None


@pytest.mark.django_db
def test_who_may_see_and_give(
    client_for, make_user, system_roles, doctor, privilege, facility_a, department_a
):
    hr = client_for(make_user(role=system_roles["hr-credentialing-officer"]))
    assert _grant(hr, doctor, privilege).status_code == 201
    head = client_for(
        make_user(
            role=system_roles["department-head"], facility=facility_a, department=department_a
        )
    )
    assert head.get(f"{API}/staff/{doctor.pk}/").json()[
        "privileges"
    ]  # may see, in their department
    assert _grant(head, doctor, privilege).status_code == 403
    assert head.post(f"{API}/clinical-privileges/", {"name": "X"}, format="json").status_code == 403
    assert client_for(make_user()).get(f"{API}/clinical-privileges/").status_code == 403


@pytest.mark.django_db
def test_giving_asks_to_confirm_it_is_you(client_for, admin_user, doctor, privilege):
    client = client_for(admin_user)
    session = client.session
    session[confirmation.SESSION_CONFIRMED_KEY] = 0
    session.save()
    response = _grant(client, doctor, privilege)
    assert response.status_code == 403 and response.json()["code"] == "REAUTH_REQUIRED"
    assert not StaffPrivilege.objects.exists()


@pytest.mark.django_db
def test_console_gives_with_the_same_rules_and_cannot_edit(admin_user, doctor, privilege):
    client = console(admin_user, confirmed=True)
    add = "/admin/staff/staffprivilege/add/"
    assert client.get(add).status_code == 200
    day = hospital_today()
    wrong = client.post(
        add,
        {
            "staff": str(doctor.pk),
            "privilege": str(privilege.pk),
            "valid_from": day.isoformat(),
            "valid_until": (day - timedelta(days=1)).isoformat(),
        },
    )
    assert wrong.status_code == 200 and "cannot be before" in wrong.content.decode()
    data = {
        "staff": str(doctor.pk),
        "privilege": str(privilege.pk),
        "valid_from": hospital_today().isoformat(),
    }
    assert client.post(add, data).status_code == 302
    grant = StaffPrivilege.objects.get()
    assert grant.granted_by == admin_user
    twice = client.post(add, data)  # the rule shows on the form, not as a server error
    assert twice.status_code == 200 and "already holds" in twice.content.decode()
    assert AuditEvent.objects.filter(action=AuditAction.STAFF_PRIVILEGE_GRANTED).count() == 1
    page = f"/admin/staff/staffprivilege/{grant.pk}/change/"
    assert client.get(page).status_code == 200
    assert client.post(page, {"note": "changed"}).status_code == 403
    client.post(
        "/admin/staff/staffprivilege/",
        {"action": "end_selected", "_selected_action": [str(grant.pk)]},
    )
    grant.refresh_from_db()
    assert grant.status == "ended" and grant.ended_by == admin_user
    staff_page = client.get(f"/admin/staff/staffmember/{doctor.pk}/change/").content.decode()
    assert "Central line insertion" in staff_page


@pytest.mark.django_db
def test_console_catalog_lists_privileges(admin_user, privilege):
    client = console(admin_user, confirmed=True)
    page = client.get("/admin/staff/clinicalprivilege/")
    assert page.status_code == 200
    assert "Central line insertion" in page.content.decode()
