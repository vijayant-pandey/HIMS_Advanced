"""HIMS-IAM-006: every session ends when a person is suspended, terminated or deactivated
(spec 13.5: "A terminated employee reuses an old session")."""

from datetime import timedelta

import pytest
from django.contrib.sessions.models import Session
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.identity.models import User, UserSession
from apps.identity.sessions import clear_expired_sessions
from apps.staff.models import StaffMember

PASSWORD = "Synthetic-Device-Passw0rd-2026"


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    from django.core.cache import cache

    cache.clear()  # these tests sign in many times; keep the 5/min login limit per test


@pytest.fixture
def doctor(organization, system_roles):
    from apps.access_control.services import assign_role

    user = User.objects.create_user(
        email="dr.devices@synthetic.test", display_name="Dr Devices", password=PASSWORD
    )
    assign_role(actor=None, user=user, role=system_roles["basic-staff"])
    StaffMember.objects.create(
        organization=organization,
        user=user,
        employee_number="EMP-S1",
        given_name="Dr",
        family_name="Devices",
        staff_type="doctor",
        joined_on="2026-01-01",
    )
    return user


def sign_in(email=None, password=PASSWORD) -> APIClient:
    """A separate 'device' that signs in through the real login endpoint."""
    device = APIClient(REMOTE_ADDR="10.0.0.7", HTTP_USER_AGENT="Synthetic Browser")
    response = device.post(
        "/api/v1/auth/login/",
        {"email": email or "dr.devices@synthetic.test", "password": password},
        format="json",
    )
    assert response.status_code == 200, response.content
    return device


def signed_in(device) -> bool:
    return device.get("/api/v1/auth/me/").status_code == 200


@pytest.mark.django_db
def test_sign_in_is_registered_and_sign_out_closes_it(doctor):
    device = sign_in()
    entry = UserSession.objects.get(user=doctor)
    assert entry.ended_at is None
    assert entry.ip_address == "10.0.0.7"
    assert entry.user_agent == "Synthetic Browser"

    device.post("/api/v1/auth/logout/")
    entry.refresh_from_db()
    assert entry.end_reason == UserSession.EndReason.LOGOUT


@pytest.mark.django_db
def test_terminating_staff_signs_them_out_on_every_device(client_for, admin_user, doctor):
    phone, laptop = sign_in(), sign_in()
    assert signed_in(phone) and signed_in(laptop)
    keys = list(UserSession.objects.filter(user=doctor).values_list("session_key", flat=True))

    staff = doctor.staff_member
    response = client_for(admin_user).patch(
        f"/api/v1/staff/{staff.pk}/",
        {"version": staff.version, "employment_status": "terminated", "left_on": "2026-06-30"},
        format="json",
    )
    assert response.status_code == 200

    assert not signed_in(phone)
    assert not signed_in(laptop)
    assert not Session.objects.filter(session_key__in=keys).exists()  # deleted, not just blocked
    assert set(UserSession.objects.filter(user=doctor).values_list("end_reason", flat=True)) == {
        UserSession.EndReason.ACCOUNT_DEACTIVATED
    }
    event = AuditEvent.objects.get(
        action=AuditAction.AUTH_SESSIONS_ENDED, resource_id=str(doctor.pk)
    )
    assert event.metadata == {"reason": "account_deactivated", "sessions_ended": 2}
    # The ending is linked to the change that caused it through the same request ID.
    update = AuditEvent.objects.get(action=AuditAction.STAFF_UPDATED, resource_id=str(staff.pk))
    assert event.request_id == update.request_id


@pytest.mark.django_db
def test_suspending_in_admin_console_signs_them_out(admin_user, doctor):
    device = sign_in()
    staff = doctor.staff_member
    console = Client()
    console.force_login(admin_user)
    prefix = {
        f"{name}-{suffix}": "0"
        for name in ("department_assignments", "qualifications", "credentials")
        for suffix in ("TOTAL_FORMS", "INITIAL_FORMS")
    }
    response = console.post(
        f"/admin/staff/staffmember/{staff.pk}/change/",
        {
            "user": str(doctor.pk),
            "employee_number": staff.employee_number,
            "given_name": staff.given_name,
            "family_name": staff.family_name,
            "staff_type": staff.staff_type,
            "employment_status": "suspended",
            "joined_on": "2026-01-01",
            **prefix,
        },
    )
    assert response.status_code == 302, response.content[:1500]
    assert not signed_in(device)


@pytest.mark.django_db
def test_deactivating_the_account_directly_signs_them_out(doctor):
    device = sign_in()
    doctor.is_active = False
    doctor.save()
    assert not signed_in(device)
    assert UserSession.objects.get(user=doctor).end_reason == "account_deactivated"


@pytest.mark.django_db
def test_other_profile_changes_do_not_sign_anyone_out(doctor):
    device = sign_in()
    doctor.display_name = "Dr Devices (Cardiology)"
    doctor.save()
    assert signed_in(device)
    assert not AuditEvent.objects.filter(action=AuditAction.AUTH_SESSIONS_ENDED).exists()


@pytest.mark.django_db
def test_reactivated_person_must_sign_in_again(doctor):
    device = sign_in()
    doctor.is_active = False
    doctor.save()
    doctor.is_active = True
    doctor.save()
    assert not signed_in(device)  # old session does not come back
    assert signed_in(sign_in())  # a fresh sign-in works


@pytest.mark.django_db
def test_password_reset_closes_every_session(doctor):
    from apps.identity.password_reset import _issue_reset, make_token

    device = sign_in()
    reset = _issue_reset(user=doctor)
    response = APIClient().post(
        "/api/v1/auth/password-reset/confirm/",
        {"token": make_token(reset), "password": "Brand-New-Passw0rd-2026"},
        format="json",
    )
    assert response.status_code == 204
    assert not signed_in(device)
    assert UserSession.objects.get(user=doctor).end_reason == "password_changed"


@pytest.mark.django_db
def test_admin_can_sign_someone_out_everywhere_without_signing_out_themselves(admin_user, doctor):
    device = sign_in()
    console = Client()
    console.force_login(admin_user)
    response = console.post(
        "/admin/identity/user/",
        {"action": "sign_out_everywhere", "_selected_action": [str(doctor.pk), str(admin_user.pk)]},
    )
    assert response.status_code == 302
    assert not signed_in(device)
    assert console.get("/admin/").status_code == 200  # the administrator stays signed in
    assert (
        AuditEvent.objects.filter(
            action=AuditAction.AUTH_SESSIONS_ENDED,
            actor_id=admin_user.pk,
            metadata__reason="signed_out_by_admin",
        ).count()
        == 2
    )


@pytest.mark.django_db
def test_admin_setting_a_password_signs_that_person_out(admin_user, doctor):
    device = sign_in()
    console = Client()
    console.force_login(admin_user)
    response = console.post(
        f"/admin/identity/user/{doctor.pk}/password/",
        {
            "password1": "Admin-Chosen-Passw0rd-26",
            "password2": "Admin-Chosen-Passw0rd-26",
            "usable_password": "true",
        },
    )
    assert response.status_code == 302, response.content[:1500]
    assert not signed_in(device)


@pytest.mark.django_db
def test_expired_sessions_are_cleaned_up(doctor):
    sign_in()
    entry = UserSession.objects.get(user=doctor)
    Session.objects.filter(session_key=entry.session_key).update(
        expire_date=timezone.now() - timedelta(minutes=1)
    )
    assert clear_expired_sessions() == 1
    entry.refresh_from_db()
    assert entry.end_reason == UserSession.EndReason.EXPIRED
    assert not Session.objects.filter(session_key=entry.session_key).exists()


@pytest.mark.django_db
def test_session_key_is_never_shown_in_the_admin(admin_user, doctor):
    sign_in()
    entry = UserSession.objects.get(user=doctor)
    console = Client()
    console.force_login(admin_user)
    page = console.get(f"/admin/identity/usersession/{entry.pk}/change/")
    assert page.status_code == 200
    assert entry.session_key.encode() not in page.content


# --- "My sign-ins" (HIMS-IAM-016) ------------------------------------------------------------


def sign_in_with(agent: str) -> APIClient:
    device = APIClient(REMOTE_ADDR="10.0.0.9", HTTP_USER_AGENT=agent)
    response = device.post(
        "/api/v1/auth/login/",
        {"email": "dr.devices@synthetic.test", "password": PASSWORD},
        format="json",
    )
    assert response.status_code == 200, response.content
    return device


CHROME_WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"
SAFARI_IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Version/18.0 Safari/604.1"


@pytest.mark.django_db
def test_people_see_their_own_sign_ins_only(doctor, make_user):
    laptop = sign_in_with(CHROME_WINDOWS)
    sign_in_with(SAFARI_IPHONE)
    other = make_user(password=PASSWORD)
    UserSession.objects.create(user=other, session_key="someone-else-key")

    rows = laptop.get("/api/v1/auth/sessions/").json()
    assert sorted(r["device"] for r in rows) == ["Chrome on Windows", "Safari on iPhone"]
    assert [r["is_current"] for r in rows if r["device"] == "Chrome on Windows"] == [True]
    assert all("session_key" not in r for r in rows)
    assert {r["ip_address"] for r in rows} == {"10.0.0.9"}


@pytest.mark.django_db
def test_sign_out_one_other_device(doctor):
    laptop = sign_in_with(CHROME_WINDOWS)
    phone = sign_in_with(SAFARI_IPHONE)
    rows = laptop.get("/api/v1/auth/sessions/").json()
    phone_row = next(r for r in rows if not r["is_current"])

    response = laptop.post(f"/api/v1/auth/sessions/{phone_row['id']}/sign-out/")
    assert response.status_code == 204
    assert not signed_in(phone)
    assert signed_in(laptop)
    entry = UserSession.objects.get(pk=phone_row["id"])
    assert entry.end_reason == UserSession.EndReason.SIGNED_OUT_BY_USER
    event = AuditEvent.objects.filter(action=AuditAction.AUTH_SESSIONS_ENDED).latest("occurred_at")
    assert event.metadata == {"reason": "signed_out_by_user", "sessions_ended": 1}
    assert str(event.actor_id) == str(doctor.pk)

    again = laptop.post(f"/api/v1/auth/sessions/{phone_row['id']}/sign-out/")
    assert again.status_code == 409
    assert again.json()["code"] == "SESSION_ALREADY_ENDED"


@pytest.mark.django_db
def test_cannot_end_this_device_or_someone_elses(doctor, make_user):
    laptop = sign_in_with(CHROME_WINDOWS)
    own = laptop.get("/api/v1/auth/sessions/").json()[0]
    response = laptop.post(f"/api/v1/auth/sessions/{own['id']}/sign-out/")
    assert response.status_code == 409
    assert response.json()["code"] == "CURRENT_SESSION"

    other = make_user(password=PASSWORD)
    theirs = UserSession.objects.create(user=other, session_key="someone-else-key-2")
    response = laptop.post(f"/api/v1/auth/sessions/{theirs.pk}/sign-out/")
    assert response.status_code == 409  # looks the same as "already ended": nothing to learn
    theirs.refresh_from_db()
    assert theirs.ended_at is None


@pytest.mark.django_db
def test_sign_out_all_other_devices_keeps_this_one(doctor):
    laptop = sign_in_with(CHROME_WINDOWS)
    phone, tablet = sign_in_with(SAFARI_IPHONE), sign_in()
    response = laptop.post("/api/v1/auth/sessions/sign-out-others/")
    assert response.status_code == 200
    assert response.json() == {"sessions_ended": 2}
    assert signed_in(laptop)
    assert not signed_in(phone) and not signed_in(tablet)
    assert [r["is_current"] for r in laptop.get("/api/v1/auth/sessions/").json()] == [True]


@pytest.mark.django_db
def test_expired_sign_ins_are_not_listed(doctor):
    laptop = sign_in_with(CHROME_WINDOWS)
    sign_in_with(SAFARI_IPHONE)
    phone_entry = UserSession.objects.get(user=doctor, user_agent=SAFARI_IPHONE)
    Session.objects.filter(session_key=phone_entry.session_key).update(
        expire_date=timezone.now() - timedelta(minutes=1)
    )
    devices = [r["device"] for r in laptop.get("/api/v1/auth/sessions/").json()]
    assert devices == ["Chrome on Windows"]


def test_device_names():
    from apps.identity.sessions import describe_device

    assert describe_device(CHROME_WINDOWS) == "Chrome on Windows"
    assert describe_device(SAFARI_IPHONE) == "Safari on iPhone"
    assert describe_device("Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Firefox/131.0") == (
        "Firefox on Linux"
    )
    assert describe_device("") == "Unknown device"
    assert describe_device("curl/8.4") == "curl/8.4"


@pytest.mark.django_db
def test_sign_ins_need_sign_in():
    assert APIClient().get("/api/v1/auth/sessions/").status_code in (401, 403)
