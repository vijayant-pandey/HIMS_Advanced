"""HIMS-IAM-021: supplier support access, the "locked box" (spec 7.2, 7.4).

All people and data are synthetic.
"""

import os
from datetime import timedelta

import pytest
from django.core import mail
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from apps.access_control import delegations
from apps.access_control.catalog import MFA_REQUIRED_PERMISSIONS, SYSTEM_ROLES, P
from apps.access_control.models import Role, RoleAssignment, SupportAccess
from apps.access_control.selectors import has_permission
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.identity.accounts import active_administrators
from apps.identity.models import User

ASK = "/api/v1/my-support-access/"
HOSPITAL = "/api/v1/support-access/"


@pytest.fixture
def supplier(make_user, system_roles):
    return make_user(
        role=system_roles["supplier-support"],
        display_name="HIMS Supplier Support",
        email="support@supplier.synthetic.test",
    )


def fresh(user) -> User:
    return User.objects.get(pk=user.pk)  # permissions are cached per user object


def ask(client, system_roles, *, role="organization-administrator", **extra):
    body = {"role": str(system_roles[role].pk), "reason": "Check the rota error", **extra}
    return client.post(ASK, body, format="json")


def test_the_supplier_role_only_asks_and_administrators_only_decide(system_roles):
    assert SYSTEM_ROLES["supplier-support"]["permissions"] == [P.SUPPORT_ACCESS_REQUEST]
    admin_codes = set(SYSTEM_ROLES["organization-administrator"]["permissions"])
    assert P.SUPPORT_ACCESS_MANAGE in admin_codes
    assert P.SUPPORT_ACCESS_REQUEST not in admin_codes
    assert {P.SUPPORT_ACCESS_REQUEST, P.SUPPORT_ACCESS_MANAGE} <= MFA_REQUIRED_PERMISSIONS
    assert system_roles["supplier-support"].is_system


def test_asking_waits_for_the_hospital_and_emails_its_administrators(
    client_for, supplier, admin_user, system_roles, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = ask(client_for(supplier), system_roles, hours=3)
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "waiting" and body["hours"] == 3 and body["kind"] == "standard"
    # Nothing is opened yet.
    assert not has_permission(fresh(supplier), P.STAFF_VIEW)
    assert [m.to for m in mail.outbox] == [[admin_user.email]]
    assert "asks for support access" in mail.outbox[0].subject
    assert AuditEvent.objects.filter(action=AuditAction.SUPPORT_ACCESS_REQUESTED).exists()
    # The hospital sees it.
    listed = client_for(admin_user).get(HOSPITAL).json()
    assert [row["id"] for row in listed] == [body["id"]]


def test_approving_gives_the_role_for_the_hours_asked(
    client_for, supplier, admin_user, system_roles, django_capture_on_commit_callbacks
):
    created = ask(client_for(supplier), system_roles).json()
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        approved = client_for(admin_user).post(
            f"{HOSPITAL}{created['id']}/approve/",
            {"version": created["version"], "note": "Go ahead"},
            format="json",
        )
    assert approved.status_code == 200, approved.content
    access = SupportAccess.objects.get()
    assert access.status == SupportAccess.Status.ACTIVE
    assert access.decided_by == admin_user
    assert access.ends_at - access.starts_at == timedelta(hours=2)
    assert access.assignment.valid_until == access.ends_at
    supplier = fresh(supplier)
    assert has_permission(supplier, P.STAFF_VIEW)
    assert supplier.support_access_until == access.ends_at
    assert [m.to for m in mail.outbox] == [[supplier.email]]
    assert "was approved" in mail.outbox[0].subject
    # Never one of the hospital's administrators, never lent as cover.
    assert supplier not in active_administrators()
    assert delegations.why_not_delegable(access.assignment)
    assert AuditEvent.objects.filter(action=AuditAction.SUPPORT_ACCESS_APPROVED).exists()


def test_the_access_ends_by_itself(client_for, supplier, admin_user, system_roles):
    created = ask(client_for(supplier), system_roles).json()
    client_for(admin_user).post(
        f"{HOSPITAL}{created['id']}/approve/", {"version": created["version"]}, format="json"
    )
    access = SupportAccess.objects.get()
    past = timezone.now() - timedelta(minutes=1)
    RoleAssignment.objects.filter(pk=access.assignment_id).update(
        valid_from=past - timedelta(hours=2), valid_until=past
    )
    SupportAccess.objects.filter(pk=access.pk).update(
        starts_at=past - timedelta(hours=2), ends_at=past
    )
    User.objects.filter(pk=supplier.pk).update(support_access_until=past)
    assert not has_permission(fresh(supplier), P.STAFF_VIEW)
    assert SupportAccess.objects.get().status == SupportAccess.Status.FINISHED
    # Not current any more; shown under past. A new request can be approved again.
    assert client_for(admin_user).get(HOSPITAL).json() == []
    assert len(client_for(admin_user).get(HOSPITAL, {"status": "past"}).json()) == 1
    again = ask(client_for(fresh(supplier)), system_roles).json()
    second = client_for(admin_user).post(
        f"{HOSPITAL}{again['id']}/approve/", {"version": again["version"]}, format="json"
    )
    assert second.status_code == 200, second.content
    assert has_permission(fresh(supplier), P.STAFF_VIEW)


def test_every_request_during_support_access_is_recorded(
    client_for, supplier, admin_user, system_roles
):
    created = ask(client_for(supplier), system_roles).json()
    client_for(admin_user).post(
        f"{HOSPITAL}{created['id']}/approve/", {"version": created["version"]}, format="json"
    )
    client = client_for(fresh(supplier))
    assert client.get("/api/v1/staff/", {"search": "Asha"}).status_code == 200
    client.get("/api/v1/facilities/", HTTP_X_HIMS_BACKGROUND="1")  # a refresh, not a click
    used = AuditEvent.objects.filter(action=AuditAction.SUPPORT_ACCESS_USED)
    assert used.count() == 1
    event = used.get()
    assert event.actor_id == supplier.pk
    assert event.metadata == {"method": "GET", "path": "/api/v1/staff/", "status": 200}
    assert "Asha" not in str(event.metadata)  # search words never reach the log
    # Nobody else's requests are recorded this way.
    client_for(admin_user).get("/api/v1/staff/")
    assert used.count() == 1


def test_emergency_access_opens_at_once_without_telling_the_hospital(
    client_for, supplier, admin_user, system_roles, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = ask(client_for(supplier), system_roles, emergency=True)
    assert response.status_code == 201, response.content
    assert response.json()["status"] == "active"
    assert response.json()["kind"] == "emergency"
    assert has_permission(fresh(supplier), P.STAFF_VIEW)
    assert mail.outbox == []  # HIMS_SUPPORT_EMERGENCY_NOTICE is off by default
    assert AuditEvent.objects.filter(action=AuditAction.SUPPORT_ACCESS_EMERGENCY_OPENED).exists()
    # Still on the hospital's records: nothing is hidden, only the email is not sent.
    assert len(client_for(admin_user).get(HOSPITAL).json()) == 1


def test_emergency_notice_can_be_switched_on(
    client_for, supplier, admin_user, system_roles, settings, django_capture_on_commit_callbacks
):
    settings.HIMS_SUPPORT_EMERGENCY_NOTICE = True
    with django_capture_on_commit_callbacks(execute=True):
        ask(client_for(supplier), system_roles, emergency=True)
    assert [m.to for m in mail.outbox] == [[admin_user.email]]
    assert "emergency support access" in mail.outbox[0].subject


def test_the_auditor_role_can_be_asked_for_separately(
    client_for, supplier, admin_user, system_roles
):
    response = ask(client_for(supplier), system_roles, role="auditor", emergency=True)
    assert response.status_code == 201, response.content
    supplier = fresh(supplier)
    assert has_permission(supplier, P.AUDIT_VIEW)
    assert not has_permission(supplier, P.STAFF_MANAGE)


@pytest.mark.parametrize(
    ("change", "status", "code"),
    [
        ({"role": "facility-administrator"}, 409, "ROLE_NOT_ASKABLE"),
        ({"hours": 9}, 409, "TOO_LONG"),
        ({"reason": "  "}, 400, None),
    ],
)
def test_unsafe_requests_are_refused(client_for, supplier, system_roles, change, status, code):
    role = change.pop("role", "organization-administrator")
    response = ask(client_for(supplier), system_roles, role=role, **change)
    assert response.status_code == status, response.content
    if code:
        assert response.json()["code"] == code
    assert not SupportAccess.objects.exists()


def test_one_request_waits_at_a_time_and_the_supplier_can_cancel_it(
    client_for, supplier, system_roles
):
    client = client_for(supplier)
    first = ask(client, system_roles).json()
    second = ask(client, system_roles)
    assert second.status_code == 409 and second.json()["code"] == "ALREADY_WAITING"
    cancelled = client.post(
        f"{ASK}{first['id']}/cancel/", {"version": first["version"]}, format="json"
    )
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert ask(client, system_roles).status_code == 201


def test_only_the_supplier_asks_and_only_the_hospital_decides(
    client_for, supplier, admin_user, system_roles
):
    # The hospital administrator holds no right to ask; the supplier none to decide.
    assert ask(client_for(admin_user), system_roles).status_code == 403
    created = ask(client_for(supplier), system_roles).json()
    own = client_for(supplier).post(
        f"{HOSPITAL}{created['id']}/approve/", {"version": created["version"]}, format="json"
    )
    assert own.status_code == 403
    assert client_for(supplier).get(HOSPITAL).status_code == 403


def test_refusing_needs_a_reason_and_tells_the_supplier(
    client_for, supplier, admin_user, system_roles, django_capture_on_commit_callbacks
):
    created = ask(client_for(supplier), system_roles).json()
    url = f"{HOSPITAL}{created['id']}/refuse/"
    blank = client_for(admin_user).post(url, {"version": created["version"]}, format="json")
    assert blank.status_code == 409 and blank.json()["code"] == "REASON_REQUIRED"
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        refused = client_for(admin_user).post(
            url, {"version": created["version"], "note": "Not today"}, format="json"
        )
    assert refused.json()["status"] == "refused"
    assert "was refused" in mail.outbox[0].subject and "Not today" in mail.outbox[0].body
    assert not has_permission(fresh(supplier), P.STAFF_VIEW)


@pytest.mark.parametrize("who", ["hospital", "supplier"])
def test_either_side_ends_running_access_early(client_for, supplier, admin_user, system_roles, who):
    created = ask(client_for(supplier), system_roles, emergency=True).json()
    if who == "hospital":
        url, client = f"{HOSPITAL}{created['id']}/end/", client_for(admin_user)
    else:
        url, client = f"{ASK}{created['id']}/end/", client_for(fresh(supplier))
    response = client.post(url, {"version": created["version"], "reason": "Done"}, format="json")
    assert response.status_code == 200, response.content
    assert response.json()["status"] == "ended_early"
    supplier = fresh(supplier)
    assert not has_permission(supplier, P.STAFF_VIEW)
    assert supplier.support_access_until is None
    assert AuditEvent.objects.filter(action=AuditAction.SUPPORT_ACCESS_ENDED).exists()


def test_the_supplier_sees_only_its_own_requests_and_the_options(
    client_for, supplier, make_user, system_roles
):
    other = make_user(role=system_roles["supplier-support"])
    ask(client_for(other), system_roles)
    ask(client_for(supplier), system_roles)
    mine = client_for(supplier).get(ASK).json()
    assert len(mine) == 1 and mine[0]["requested_by"]["id"] == str(supplier.pk)
    options = client_for(supplier).get(f"{ASK}options/").json()
    assert {r["code"] for r in options["roles"]} == {"organization-administrator", "auditor"}
    assert options["default_hours"] == 2 and options["max_hours"] == 8
    assert options["emergency_notice"] is False


def test_admin_console_approves_and_ends(client_for, supplier, admin_user, system_roles):
    created = ask(client_for(supplier), system_roles).json()
    console = Client()
    console.force_login(admin_user)
    url = "/admin/access_control/supportaccess/"
    assert console.get(url).status_code == 200
    console.post(url, {"action": "approve_selected", "_selected_action": [created["id"]]})
    access = SupportAccess.objects.get()
    assert access.status == SupportAccess.Status.ACTIVE and access.decided_by == admin_user
    assert console.get(f"{url}{access.pk}/change/").status_code == 200
    assert console.get(f"{url}add/").status_code == 403
    console.post(url, {"action": "end_selected", "_selected_action": [created["id"]]})
    assert SupportAccess.objects.get().status == SupportAccess.Status.ENDED_EARLY


def test_provisioning_can_create_the_supplier_account(db):
    os.environ["HIMS_TEST_SUPPLIER_PW"] = "Synthetic-Supplier-Passw0rd-0021"
    try:
        call_command(
            "provision_organization",
            "--legal-name=Synthetic Supplier Test Pvt Ltd",
            "--display-name=Synthetic Supplier Test",
            "--country=IN",
            "--timezone=Asia/Kolkata",
            "--currency=INR",
            "--admin-email=admin@supplier-test.synthetic.test",
            "--admin-name=Synthetic Admin",
            "--support-email=support@supplier-test.synthetic.test",
            "--support-password-env=HIMS_TEST_SUPPLIER_PW",
        )
    finally:
        del os.environ["HIMS_TEST_SUPPLIER_PW"]
    supplier = User.objects.get(email="support@supplier-test.synthetic.test")
    assert supplier.has_usable_password()
    assert list(
        RoleAssignment.objects.filter(user=supplier).values_list("role__code", flat=True)
    ) == ["supplier-support"]
    assert Role.objects.filter(code="supplier-support", is_system=True).exists()
