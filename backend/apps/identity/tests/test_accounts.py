"""Accounts screen, including people who are not staff (HIMS-IAM-015). Synthetic data only."""

import pytest
from django.test import Client, override_settings

from apps.access_control.services import create_role
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.identity.models import Invitation, UserSession
from apps.staff.models import StaffMember

API = "/api/v1/accounts"


@pytest.fixture
def it_support(make_user, organization):
    """Can manage accounts but is not a hospital administrator (to test the lock-out rule)."""
    role = create_role(
        actor=None,
        organization=organization,
        code="it-support",
        name="IT support",
        permissions=["accounts.manage", "access.roles.view"],
    )
    return make_user(role=role, display_name="Synthetic IT")


def _row(client, user):
    return next(r for r in client.get(API + "/").json()["results"] if r["id"] == str(user.pk))


@pytest.mark.django_db
def test_lists_accounts_with_roles_and_kind(client_for, admin_user, auditor_user, organization):
    StaffMember.objects.create(
        organization=organization,
        user=auditor_user,
        employee_number="EMP-1",
        given_name="A",
        family_name="B",
        staff_type="administrator",
        joined_on="2026-01-01",
    )
    client = client_for(admin_user)
    admin_row = _row(client, admin_user)
    assert admin_row["roles"] == ["Organization administrator"]
    assert admin_row["staff_member_id"] is None
    not_staff = client.get(API + "/", {"kind": "not_staff"}).json()["results"]
    assert str(admin_user.pk) in {r["id"] for r in not_staff}
    assert str(auditor_user.pk) not in {r["id"] for r in not_staff}
    assert client.get(API + "/", {"search": auditor_user.email[:8]}).json()["count"] == 1


@pytest.mark.django_db
def test_add_account_for_someone_who_is_not_staff(client_for, admin_user):
    client = client_for(admin_user)
    body = {
        "email": "Ext.Auditor@Synthetic.test",
        "display_name": "External Auditor",
        "reason": "FY audit",
    }
    created = client.post(API + "/", body, format="json")
    assert created.status_code == 201
    row = created.json()
    assert row["email"] == "ext.auditor@synthetic.test"
    assert row["activated"] is False and row["invitation_expires_at"] is not None
    assert row["roles"] == []  # no access until a role is given
    assert Invitation.objects.filter(user_id=row["id"]).count() == 1
    event = AuditEvent.objects.get(action=AuditAction.ACCOUNT_CREATED)
    assert event.reason == "FY audit"
    assert client.post(API + "/", body, format="json").json()["code"] == "USER_EMAIL_EXISTS"


@pytest.mark.django_db
def test_switch_off_and_on_ends_sessions_and_is_audited(client_for, admin_user, make_user):
    vendor = make_user(display_name="Vendor Engineer", password="Synthetic-Vendor-Passw0rd-2026")
    signed_in = Client()
    signed_in.post(
        "/api/v1/auth/login/",
        {"email": vendor.email, "password": "Synthetic-Vendor-Passw0rd-2026"},
        content_type="application/json",
    )
    client = client_for(admin_user)
    off = client.post(f"{API}/{vendor.pk}/deactivate/", {"reason": "Contract ended"}, format="json")
    assert off.status_code == 200 and off.json()["is_active"] is False
    assert not UserSession.objects.filter(user=vendor, ended_at__isnull=True).exists()
    assert AuditEvent.objects.get(action=AuditAction.ACCOUNT_DEACTIVATED).reason == "Contract ended"
    on = client.post(f"{API}/{vendor.pk}/reactivate/", {"reason": "Renewed"}, format="json")
    assert on.json()["is_active"] is True


@pytest.mark.django_db
def test_own_and_staff_accounts_are_not_switched_here(
    client_for, admin_user, make_user, organization
):
    client = client_for(admin_user)
    own = client.post(f"{API}/{admin_user.pk}/deactivate/", {"reason": "x"}, format="json")
    assert own.json()["code"] == "SELF_ACCOUNT_CHANGE"
    nurse = make_user()
    StaffMember.objects.create(
        organization=organization,
        user=nurse,
        employee_number="EMP-2",
        given_name="N",
        family_name="S",
        staff_type="nurse",
        joined_on="2026-01-01",
    )
    staff = client.post(f"{API}/{nurse.pk}/deactivate/", {"reason": "x"}, format="json")
    assert staff.json()["code"] == "ACCOUNT_FOLLOWS_EMPLOYMENT"


@pytest.mark.django_db
def test_the_last_administrator_can_never_be_switched_off(
    client_for, admin_user, it_support, make_user, system_roles
):
    client = client_for(it_support)
    refused = client.post(f"{API}/{admin_user.pk}/deactivate/", {"reason": "x"}, format="json")
    assert refused.status_code == 409
    assert refused.json()["code"] == "LAST_ADMINISTRATOR"
    admin_user.refresh_from_db()
    assert admin_user.is_active

    # With a second active administrator, the first one can be switched off.
    make_user(role=system_roles["organization-administrator"])
    ok = client.post(f"{API}/{admin_user.pk}/deactivate/", {"reason": "Left"}, format="json")
    assert ok.status_code == 200 and ok.json()["is_active"] is False


@pytest.mark.django_db
def test_terminating_the_last_administrator_on_the_staff_page_is_refused(
    client_for, admin_user, make_user, system_roles, organization
):
    StaffMember.objects.create(
        organization=organization,
        user=admin_user,
        employee_number="EMP-ADM",
        given_name="Admin",
        family_name="Person",
        staff_type="administrator",
        joined_on="2026-01-01",
    )
    staff = StaffMember.objects.get(user=admin_user)
    hr = client_for(make_user(role=system_roles["hr-credentialing-officer"]))
    response = hr.patch(
        f"/api/v1/staff/{staff.pk}/",
        {"version": 1, "employment_status": "terminated"},
        format="json",
    )
    assert response.status_code == 409
    assert response.json()["code"] == "LAST_ADMINISTRATOR"
    admin_user.refresh_from_db()
    assert admin_user.is_active


@pytest.mark.django_db
def test_admin_console_refuses_switching_off_the_last_administrator(
    admin_user, make_user, organization
):
    operator_role = create_role(
        actor=None,
        organization=organization,
        code="console-operator",
        name="Console operator",
        permissions=["platform.admin_console"],
    )
    console = Client()
    console.force_login(make_user(role=operator_role))
    page = console.post(
        f"/admin/identity/user/{admin_user.pk}/change/",
        {
            "email": admin_user.email,
            "display_name": admin_user.display_name,
            "is_active": "",
            "role_assignments-TOTAL_FORMS": "0",
            "role_assignments-INITIAL_FORMS": "0",
        },
    )
    assert page.status_code == 200  # form shown again with the message
    assert b"last active hospital administrator" in page.content
    admin_user.refresh_from_db()
    assert admin_user.is_active


@pytest.mark.django_db
def test_reset_two_factor_and_sign_out(client_for, admin_user, make_user):
    person = make_user()
    client = client_for(admin_user)
    assert client.post(f"{API}/{person.pk}/reset-two-factor/").status_code == 200
    assert client.post(f"{API}/{person.pk}/sign-out-everywhere/").status_code == 200
    assert AuditEvent.objects.filter(action=AuditAction.AUTH_MFA_RESET).exists()


@pytest.mark.django_db
def test_invitation_only_for_accounts_not_activated(client_for, admin_user, make_user):
    client = client_for(admin_user)
    activated = make_user(password="Synthetic-Done-Passw0rd-2026")
    assert client.post(f"{API}/{activated.pk}/invitation/").json()["code"] == "NOT_INVITABLE"
    pending = make_user()
    assert client.post(f"{API}/{pending.pk}/invitation/").status_code == 200


@pytest.mark.django_db
def test_permissions(client_for, make_user, system_roles):
    basic = client_for(make_user(role=system_roles["basic-staff"]))
    assert basic.get(API + "/").status_code == 403
    hr = client_for(make_user(role=system_roles["hr-credentialing-officer"]))
    body = {"email": "x@synthetic.test", "display_name": "X", "reason": "x"}
    assert hr.post(API + "/", body, format="json").status_code == 403


@pytest.mark.django_db
def test_managing_accounts_requires_two_factor(it_support):
    from apps.identity.mfa import is_required

    with override_settings(HIMS_MFA_REQUIRED_FOR_PRIVILEGED=True):
        assert is_required(it_support)
