"""Confirm it's you before a sensitive action (HIMS-IAM-007; spec 13.1). Synthetic data."""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from django.utils import timezone

from apps.access_control.api.delegation_views import AccessDelegationViewSet
from apps.access_control.api.views import (
    AccessReviewViewSet,
    RoleAssignmentViewSet,
    RoleViewSet,
)
from apps.audit.api.views import AuditEventViewSet
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.features.api.views import FeatureChangeView
from apps.features.catalog import F
from apps.features.services import set_feature
from apps.identity import confirmation, mfa
from apps.identity.api.account_views import AccountViewSet
from apps.identity.models import MfaDevice
from apps.staff.models import StaffMember
from common.crypto import encrypt

PASSWORD = "Synthetic-Confirm-Passw0rd-2026"
STATUS = "/api/v1/auth/confirm-identity/"
END = "/api/v1/auth/confirm-identity/end/"
ACCOUNTS = "/api/v1/accounts/"
AUDIT_EXPORT = "/api/v1/audit-events/export/"


@pytest.fixture(autouse=True)
def _reset_throttle():
    cache.clear()


@pytest.fixture
def admin(admin_user):
    admin_user.set_password(PASSWORD)
    admin_user.save(update_fields=["password"])
    return admin_user


@pytest.fixture
def nurse(organization, make_user):
    return StaffMember.objects.create(
        organization=organization,
        user=make_user(),
        employee_number="EMP-CONF-1",
        given_name="Mary",
        family_name="Confirm",
        staff_type="nurse",
        joined_on="2026-01-05",
    )


def _stale(client):
    """As if the person signed in longer ago than the confirmation lasts."""
    session = client.session
    session[confirmation.SESSION_CONFIRMED_KEY] = (timezone.now() - timedelta(hours=1)).timestamp()
    session.save()


def _with_authenticator(user):
    secret = mfa.new_secret()
    MfaDevice.objects.update_or_create(
        user=user,
        defaults={"secret_encrypted": encrypt(secret), "confirmed_at": timezone.now()},
    )
    session_step = mfa.current_step()
    return mfa.totp(secret, session_step)


def _deactivate(client, account):
    return client.post(f"{ACCOUNTS}{account.pk}/deactivate/", {"reason": "Left"}, format="json")


def test_every_sensitive_action_stays_declared():
    """Removing one of these must be a decision, not an accident."""
    assert set(RoleViewSet.sensitive_actions) == {"create", "partial_update"}
    assert set(RoleAssignmentViewSet.sensitive_actions) == {"create", "revoke"}
    assert set(AccessReviewViewSet.sensitive_actions) == {"decide", "export"}
    assert set(AccessDelegationViewSet.sensitive_actions) == {"create"}
    assert set(AccountViewSet.sensitive_actions) == {
        "create",
        "deactivate",
        "reactivate",
        "reset_two_factor",
        "sign_out_everywhere",
    }
    assert set(FeatureChangeView.sensitive_actions) == {"post"}
    assert set(AuditEventViewSet.sensitive_actions) == {"export"}


@pytest.mark.django_db
def test_signing_in_counts_as_confirming(client_for, admin, make_user):
    client = client_for(admin)
    assert client.get(STATUS).json()["confirmed"] is True
    assert _deactivate(client, make_user()).status_code == 200


@pytest.mark.django_db
def test_sensitive_action_is_refused_when_the_confirmation_is_old(client_for, admin, make_user):
    client = client_for(admin)
    _stale(client)
    response = _deactivate(client, make_user())
    assert response.status_code == 403
    assert response.json()["code"] == "REAUTH_REQUIRED"
    assert not AuditEvent.objects.filter(action=AuditAction.ACCESS_DENIED).exists()


@pytest.mark.django_db
def test_no_permission_is_refused_first_and_never_asks_to_confirm(client_for, make_user):
    client = client_for(make_user())
    _stale(client)
    response = _deactivate(client, make_user())
    assert response.status_code == 403
    assert response.json()["code"] != "REAUTH_REQUIRED"


@pytest.mark.django_db
def test_non_sensitive_actions_are_not_affected(client_for, admin):
    client = client_for(admin)
    _stale(client)
    assert client.get(ACCOUNTS).status_code == 200


@pytest.mark.django_db
def test_right_password_confirms_and_the_action_then_works(client_for, admin, make_user):
    client = client_for(admin)
    _stale(client)
    response = client.post(STATUS, {"password": PASSWORD}, format="json")
    assert response.status_code == 200
    body = response.json()
    assert body["confirmed"] is True and body["confirmed_until"]
    assert _deactivate(client, make_user()).status_code == 200
    event = AuditEvent.objects.get(action=AuditAction.AUTH_IDENTITY_CONFIRMED)
    assert event.actor_id == admin.pk
    assert event.metadata["method"] == "password"


@pytest.mark.django_db
def test_wrong_password_is_refused_and_audited(client_for, admin):
    client = client_for(admin)
    _stale(client)
    response = client.post(STATUS, {"password": "Synthetic-Wrong-Passw0rd-1234"}, format="json")
    assert response.status_code == 400
    assert response.json()["code"] == "REAUTH_FAILED"
    assert AuditEvent.objects.filter(action=AuditAction.AUTH_IDENTITY_CONFIRM_FAILED).exists()
    assert client.get(STATUS).json()["confirmed"] is False


@pytest.mark.django_db
def test_two_factor_users_need_the_code_as_well(client_for, admin):
    code = _with_authenticator(admin)
    client = client_for(admin)
    session = client.session
    session[mfa.SESSION_VERIFIED_KEY] = True
    session.save()
    _stale(client)
    assert client.get(STATUS).json()["needs_code"] is True
    assert client.post(STATUS, {"password": PASSWORD}, format="json").status_code == 400
    assert (
        client.post(STATUS, {"password": PASSWORD, "code": "000000"}, format="json").status_code
        == 400
    )
    response = client.post(STATUS, {"password": PASSWORD, "code": code}, format="json")
    assert response.status_code == 200
    # The same code cannot be used twice.
    _stale(client)
    assert (
        client.post(STATUS, {"password": PASSWORD, "code": code}, format="json").status_code == 400
    )


@pytest.mark.django_db
def test_right_code_with_wrong_password_does_not_use_up_the_code(client_for, admin):
    code = _with_authenticator(admin)
    client = client_for(admin)
    session = client.session
    session[mfa.SESSION_VERIFIED_KEY] = True
    session.save()
    _stale(client)
    wrong = {"password": "Synthetic-Wrong-Passw0rd-1234", "code": code}
    assert client.post(STATUS, wrong, format="json").status_code == 400
    assert (
        client.post(STATUS, {"password": PASSWORD, "code": code}, format="json").status_code == 200
    )


@pytest.mark.django_db
def test_five_wrong_tries_end_the_session(client_for, admin):
    client = client_for(admin)
    _stale(client)
    bad = {"password": "Synthetic-Wrong-Passw0rd-1234"}
    for _ in range(confirmation.MAX_FAILURES - 1):
        assert client.post(STATUS, bad, format="json").status_code == 400
    response = client.post(STATUS, bad, format="json")
    assert response.status_code == 401
    assert response.json()["code"] == "REAUTH_LOCKED"
    assert AuditEvent.objects.filter(action=AuditAction.AUTH_IDENTITY_CONFIRM_LOCKED).exists()
    assert client.get(ACCOUNTS).status_code in (401, 403)


@pytest.mark.django_db
def test_a_right_try_clears_the_wrong_tries(client_for, admin):
    client = client_for(admin)
    _stale(client)
    bad = {"password": "Synthetic-Wrong-Passw0rd-1234"}
    for _ in range(confirmation.MAX_FAILURES - 1):
        client.post(STATUS, bad, format="json")
    assert client.post(STATUS, {"password": PASSWORD}, format="json").status_code == 200
    assert client.post(STATUS, bad, format="json").status_code == 400


@pytest.mark.django_db
def test_end_now_asks_again_next_time(client_for, admin, make_user):
    client = client_for(admin)
    body = client.post(END, format="json").json()
    assert body["confirmed"] is False and body["confirmed_until"] is None
    assert _deactivate(client, make_user()).status_code == 403


@pytest.mark.django_db
def test_signed_out_people_get_no_status(client_for):
    assert client_for().get(STATUS).status_code in (401, 403)


@pytest.mark.django_db
def test_the_hospital_can_turn_it_off(client_for, admin, make_user):
    client = client_for(admin)
    _stale(client)
    set_feature(
        actor=admin, key=F.CONFIRM_SENSITIVE_ACTIONS, enabled=False, reason="Testing", version=0
    )
    body = client.get(STATUS).json()
    assert body["enabled"] is False and body["confirmed"] is True
    assert _deactivate(client, make_user()).status_code == 200


@pytest.mark.django_db
@override_settings(HIMS_CONFIRM_IDENTITY_MINUTES=5)
def test_how_long_it_lasts_is_a_setting(client_for, admin):
    client = client_for(admin)
    assert client.get(STATUS).json()["window_minutes"] == 5
    session = client.session
    session[confirmation.SESSION_CONFIRMED_KEY] = (
        timezone.now() - timedelta(minutes=6)
    ).timestamp()
    session.save()
    assert client.get(STATUS).json()["confirmed"] is False


@pytest.mark.django_db
def test_audit_export_asks_too(client_for, auditor_user):
    client = client_for(auditor_user)
    session = client.session
    session[mfa.SESSION_VERIFIED_KEY] = True
    session.save()
    assert client.get(AUDIT_EXPORT).status_code == 200
    _stale(client)
    response = client.get(AUDIT_EXPORT)
    assert response.status_code == 403
    assert response.json()["code"] == "REAUTH_REQUIRED"


@pytest.mark.django_db
def test_suspending_or_terminating_staff_asks_but_other_edits_do_not(client_for, admin, nurse):
    client = client_for(admin)
    _stale(client)
    url = f"/api/v1/staff/{nurse.pk}/"
    edit = client.patch(url, {"version": nurse.version, "given_name": "Asha"}, format="json")
    assert edit.status_code == 200
    version = edit.json()["version"]
    refused = client.patch(
        url, {"version": version, "employment_status": "terminated"}, format="json"
    )
    assert refused.status_code == 403
    assert refused.json()["code"] == "REAUTH_REQUIRED"


# --- Admin console ----------------------------------------------------------------------------


def _console(user):
    console = Client()
    console.force_login(user)
    session = console.session
    session[mfa.SESSION_VERIFIED_KEY] = True
    session.save()
    return console


@pytest.mark.django_db
def test_console_sends_an_old_confirmation_to_the_confirm_page(admin, make_user):
    console = _console(admin)
    target = make_user()
    url = "/admin/identity/user/"
    _stale(console)
    assert console.get(url).status_code == 200  # looking is fine
    response = console.post(
        url, {"action": "sign_out_everywhere", "_selected_action": [str(target.pk)]}
    )
    assert response.status_code == 302
    assert response.url.startswith("/admin/confirm-identity/?next=")


@pytest.mark.django_db
def test_console_confirm_page_accepts_the_password_and_goes_back(admin):
    console = _console(admin)
    _stale(console)
    page = console.get("/admin/confirm-identity/?next=/admin/identity/user/")
    assert page.status_code == 200
    assert b"Confirm it&#x27;s you" in page.content or b"Confirm it's you" in page.content
    wrong = console.post(
        "/admin/confirm-identity/",
        {"password": "Synthetic-Wrong-Passw0rd-1234", "next": "/admin/identity/user/"},
    )
    assert wrong.status_code == 200
    assert b"not accepted" in wrong.content
    done = console.post(
        "/admin/confirm-identity/", {"password": PASSWORD, "next": "/admin/identity/user/"}
    )
    assert done.status_code == 302
    assert done.url == "/admin/identity/user/"
    assert AuditEvent.objects.filter(action=AuditAction.AUTH_IDENTITY_CONFIRMED).exists()


@pytest.mark.django_db
def test_console_never_redirects_to_another_site(admin):
    console = _console(admin)
    done = console.post(
        "/admin/confirm-identity/", {"password": PASSWORD, "next": "https://evil.example/"}
    )
    assert done.status_code == 302
    assert done.url == "/admin/"


@pytest.mark.django_db
def test_console_five_wrong_tries_sign_out(admin):
    console = _console(admin)
    bad = {"password": "Synthetic-Wrong-Passw0rd-1234", "next": "/admin/"}
    for _ in range(confirmation.MAX_FAILURES - 1):
        assert console.post("/admin/confirm-identity/", bad).status_code == 200
    response = console.post("/admin/confirm-identity/", bad)
    assert response.status_code == 302
    assert "/admin/login/" in response.url
