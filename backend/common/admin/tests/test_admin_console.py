"""The admin console honours HIMS RBAC, audit and domain rules (ADR-016)."""

import pytest
from django.core.cache import cache
from django.test import Client

from apps.access_control.catalog import P
from apps.access_control.models import RoleAssignment
from apps.access_control.services import create_role
from apps.audit.models import AuditEvent
from apps.facilities.models import Facility
from apps.identity.models import User
from apps.staff.models import StaffMember
from common.outbox.models import OutboxEvent

PASSWORD = "Synthetic-Console-Passw0rd"


@pytest.fixture(autouse=True)
def _clear_lockouts():
    cache.clear()


def console(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_admin_can_open_console_and_all_domain_pages(admin_user):
    client = console(admin_user)
    assert client.get("/admin/").status_code == 200
    for url in [
        "/admin/organizations/organization/",
        "/admin/facilities/facility/",
        "/admin/facilities/facility/add/",
        "/admin/identity/user/",
        "/admin/identity/user/add/",
        "/admin/access_control/role/",
        "/admin/access_control/roleassignment/add/",
        "/admin/staff/staffmember/add/",
        "/admin/staff/staffcredential/",
        "/admin/outbox/outboxevent/",
    ]:
        assert client.get(url).status_code == 200, url


@pytest.mark.django_db
def test_user_without_console_permission_is_sent_to_login(make_user):
    response = console(make_user()).get("/admin/")
    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


@pytest.mark.django_db
def test_admin_cannot_see_audit_log_but_auditor_can(admin_user, auditor_user):
    assert console(admin_user).get("/admin/audit/auditevent/").status_code == 403
    auditor = console(auditor_user)
    assert auditor.get("/admin/audit/auditevent/").status_code == 200
    assert auditor.get("/admin/facilities/facility/").status_code == 403
    assert AuditEvent.objects.filter(
        action="audit.events.searched", actor_id=auditor_user.pk
    ).exists()


@pytest.mark.django_db
def test_console_login_checks_rbac_and_is_audited(make_user, system_roles):
    admin = make_user(role=system_roles["organization-administrator"], password=PASSWORD)
    nobody = make_user(password=PASSWORD)
    client = Client()

    denied = client.post("/admin/login/", {"username": nobody.email, "password": PASSWORD})
    assert denied.status_code == 200  # form re-rendered with an error

    ok = client.post("/admin/login/", {"username": admin.email, "password": PASSWORD})
    assert ok.status_code == 302
    assert AuditEvent.objects.filter(action="auth.login", actor_id=admin.pk).exists()


@pytest.mark.django_db
def test_console_login_locks_out_after_repeated_failures(make_user, system_roles):
    admin = make_user(role=system_roles["organization-administrator"], password=PASSWORD)
    client = Client()
    for _ in range(5):
        client.post("/admin/login/", {"username": admin.email, "password": "wrong"})
    locked = client.post("/admin/login/", {"username": admin.email, "password": PASSWORD})
    assert locked.status_code == 200
    assert b"Too many failed sign-in attempts" in locked.content


@pytest.mark.django_db
def test_creating_a_facility_in_console_is_audited(admin_user, organization):
    response = console(admin_user).post(
        "/admin/facilities/facility/add/",
        {
            "code": "west",
            "name": "West Branch",
            "facility_type": "hospital",
            "status": "active",
            "country": "IN",
            "state_region": "Maharashtra",
            "city": "Pune",
            "address_line1": "4 Synthetic Road",
            "postal_code": "411001",
            "timezone": "Asia/Kolkata",
            "departments-TOTAL_FORMS": "1",
            "departments-INITIAL_FORMS": "0",
            "buildings-TOTAL_FORMS": "0",  # buildings section (HIMS-FAC-004)
            "buildings-INITIAL_FORMS": "0",
            "departments-0-code": "er",
            "departments-0-name": "Emergency",
            "departments-0-department_type": "clinical",
            "departments-0-status": "active",
        },
    )
    assert response.status_code == 302, response.content[:2000]
    facility = Facility.objects.get(code="west")
    assert facility.organization_id == organization.pk
    assert facility.departments.get().code == "er"
    assert AuditEvent.objects.filter(
        action="admin.facility.created", resource_id=str(facility.pk)
    ).exists()
    assert AuditEvent.objects.filter(action="admin.department.created").exists()


@pytest.mark.django_db
def test_console_edit_bumps_version_and_records_diff(admin_user, facility_a):
    data = {
        "code": facility_a.code,
        "name": "Renamed Facility",
        "facility_type": facility_a.facility_type,
        "status": "active",
        "country": "IN",
        "state_region": facility_a.state_region,
        "city": facility_a.city,
        "address_line1": facility_a.address_line1,
        "postal_code": facility_a.postal_code,
        "timezone": facility_a.timezone,
        "departments-TOTAL_FORMS": "0",
        "departments-INITIAL_FORMS": "0",
        "buildings-TOTAL_FORMS": "0",  # buildings section (HIMS-FAC-004)
        "buildings-INITIAL_FORMS": "0",
    }
    response = console(admin_user).post(f"/admin/facilities/facility/{facility_a.pk}/change/", data)
    assert response.status_code == 302
    facility_a.refresh_from_db()
    assert facility_a.version == 2
    event = AuditEvent.objects.get(action="admin.facility.updated")
    assert event.changes["after"]["name"] == "Renamed Facility"


@pytest.mark.django_db
def test_nothing_can_be_deleted_from_console(admin_user, facility_a):
    response = console(admin_user).post(
        f"/admin/facilities/facility/{facility_a.pk}/delete/", {"post": "yes"}
    )
    assert response.status_code == 403
    assert Facility.objects.filter(pk=facility_a.pk).exists()


@pytest.mark.django_db
def test_console_cannot_be_used_to_grant_audit_access(admin_user, system_roles, make_user):
    target = make_user()
    response = console(admin_user).post(
        "/admin/access_control/roleassignment/add/",
        {"user": str(target.pk), "role": str(system_roles["auditor"].pk), "reason": "x"},
    )
    assert response.status_code == 200  # form error, not saved
    assert b"cannot grant permissions you do not hold" in response.content
    assert not RoleAssignment.objects.filter(user=target).exists()


@pytest.mark.django_db
def test_console_role_grant_uses_service_and_audit(admin_user, organization, facility_a, make_user):
    role = create_role(
        actor=None,
        organization=organization,
        code="viewer",
        name="Viewer",
        permissions=[P.FACILITIES_VIEW],
    )
    target = make_user()
    response = console(admin_user).post(
        "/admin/access_control/roleassignment/add/",
        {
            "user": str(target.pk),
            "role": str(role.pk),
            "facility": str(facility_a.pk),
            "reason": "x",
        },
    )
    assert response.status_code == 302
    assignment = RoleAssignment.objects.get(user=target)
    assert assignment.granted_by_id == admin_user.pk
    assert AuditEvent.objects.filter(
        action="access.role.assigned", resource_id=str(assignment.pk)
    ).exists()


@pytest.mark.django_db
def test_terminating_staff_in_console_disables_login(admin_user, organization):
    user = User.objects.create_user(
        email="nurse@synthetic.test", display_name="Nurse", password=PASSWORD
    )
    staff = StaffMember.objects.create(
        organization=organization,
        user=user,
        employee_number="EMP-77",
        given_name="N",
        family_name="Urse",
        staff_type="nurse",
        joined_on="2026-01-01",
    )
    prefix = {
        f"{name}-{suffix}": "0"
        for name in ("department_assignments", "qualifications", "credentials")
        for suffix in ("TOTAL_FORMS", "INITIAL_FORMS")
    }
    response = console(admin_user).post(
        f"/admin/staff/staffmember/{staff.pk}/change/",
        {
            "user": str(user.pk),
            "employee_number": "EMP-77",
            "given_name": "N",
            "family_name": "Urse",
            "staff_type": "nurse",
            "employment_status": "terminated",
            "joined_on": "2026-01-01",
            "left_on": "2026-02-01",
            **prefix,
        },
    )
    assert response.status_code == 302, response.content[:2000]
    user.refresh_from_db()
    assert not user.is_active
    assert OutboxEvent.objects.filter(event_type="staff.member.employment_status_changed").exists()


@pytest.mark.django_db
def test_console_follows_shared_theme_cookie(admin_user):
    client = console(admin_user)
    client.cookies["hims_theme"] = "red"
    assert b"--primary: #c62828" in client.get("/admin/").content

    client.cookies["hims_theme"] = "</style><script>alert(1)</script>"
    page = client.get("/admin/").content
    assert b"--primary: #1565c0" in page  # unknown values fall back to blue
    assert b"<script>alert(1)" not in page
