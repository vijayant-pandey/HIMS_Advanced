"""Two-factor sign-in (HIMS-IAM-005; spec 4.4, 13.1, 13.3)."""

import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from django.core.cache import cache
from django.test import Client, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.identity import mfa
from apps.identity.models import MfaDevice, MfaRecoveryCode, UserSession
from common import crypto

PASSWORD = "Synthetic-Mfa-Passw0rd-2026"
ENFORCED = override_settings(HIMS_MFA_REQUIRED_FOR_PRIVILEGED=True)


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    cache.clear()


def code_for(user, step_offset=0) -> str:
    secret = crypto.decrypt(MfaDevice.objects.get(user=user).secret_encrypted)
    return mfa.totp(secret, mfa.current_step() + step_offset)


def enable_mfa(client, user) -> list[str]:
    assert client.post("/api/v1/auth/mfa/setup/").status_code == 201
    response = client.post("/api/v1/auth/mfa/confirm/", {"code": code_for(user)}, format="json")
    assert response.status_code == 200, response.content
    return response.json()["recovery_codes"]


def password_step(email, password=PASSWORD) -> tuple[APIClient, object]:
    device = APIClient()
    response = device.post(
        "/api/v1/auth/login/", {"email": email, "password": password}, format="json"
    )
    return device, response


@pytest.fixture
def admin(make_user, system_roles):
    return make_user(role=system_roles["organization-administrator"], password=PASSWORD)


@pytest.fixture
def nurse(make_user, system_roles):
    return make_user(role=system_roles["basic-staff"], password=PASSWORD)


# --- Algorithm and storage -----------------------------------------------------------------


def test_totp_matches_rfc_6238_test_vectors():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32 of "12345678901234567890"
    assert mfa.totp(secret, 59 // 30, digits=8) == "94287082"
    assert mfa.totp(secret, 1111111109 // 30, digits=8) == "07081804"
    assert mfa.totp(secret, 1234567890 // 30, digits=8) == "89005924"
    assert mfa.totp(secret, 20000000000 // 30, digits=8) == "65353130"


def test_codes_from_one_step_either_side_are_accepted():
    secret = mfa.new_secret()
    now = 1_800_000_000
    step = mfa.current_step(now)
    assert mfa.matching_step(secret, mfa.totp(secret, step - 1), now=now) == step - 1
    assert mfa.matching_step(secret, mfa.totp(secret, step + 1), now=now) == step + 1
    assert mfa.matching_step(secret, mfa.totp(secret, step + 2), now=now) is None


@pytest.mark.django_db
def test_secret_is_encrypted_and_recovery_codes_are_only_fingerprints(client_for, nurse):
    client = client_for(nurse)
    secret = client.post("/api/v1/auth/mfa/setup/").json()["secret"]
    device = MfaDevice.objects.get(user=nurse)
    assert secret not in device.secret_encrypted
    assert crypto.decrypt(device.secret_encrypted) == secret

    codes = client.post(
        "/api/v1/auth/mfa/confirm/", {"code": code_for(nurse)}, format="json"
    ).json()["recovery_codes"]
    assert len(codes) == 10
    stored = set(MfaRecoveryCode.objects.filter(user=nurse).values_list("code_hash", flat=True))
    assert not any(code in stored for code in codes)


@override_settings(HIMS_FIELD_ENCRYPTION_KEYS=[Fernet.generate_key().decode()])
def test_encryption_keys_can_be_rotated():
    from django.conf import settings

    token = crypto.encrypt("authenticator-secret")
    with override_settings(
        HIMS_FIELD_ENCRYPTION_KEYS=[
            Fernet.generate_key().decode(),
            *settings.HIMS_FIELD_ENCRYPTION_KEYS,
        ]
    ):
        assert crypto.decrypt(token) == "authenticator-secret"  # old key still decrypts
    with (
        override_settings(HIMS_FIELD_ENCRYPTION_KEYS=[Fernet.generate_key().decode()]),
        pytest.raises(crypto.DecryptionError),
    ):
        crypto.decrypt(token)


# --- Setup ------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_setup_returns_qr_data_and_wrong_first_code_is_rejected(client_for, nurse):
    client = client_for(nurse)
    setup = client.post("/api/v1/auth/mfa/setup/").json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/HIMS%20%28Synthetic%20Health%29")
    assert f"secret={setup['secret']}" in setup["otpauth_uri"]

    wrong = client.post("/api/v1/auth/mfa/confirm/", {"code": "000000"}, format="json")
    assert wrong.status_code == 400
    assert wrong.json()["code"] == "MFA_CODE_INVALID"
    assert MfaDevice.objects.get(user=nurse).confirmed_at is None

    enable_mfa_codes = client.post(
        "/api/v1/auth/mfa/confirm/", {"code": code_for(nurse)}, format="json"
    )
    assert enable_mfa_codes.status_code == 200
    status = client.get("/api/v1/auth/mfa/").json()
    assert status == {
        "enabled": True,
        "required": False,
        "verified": True,
        "recovery_codes_remaining": 10,
    }
    assert AuditEvent.objects.filter(
        action=AuditAction.AUTH_MFA_ENABLED, actor_id=nurse.pk
    ).exists()


# --- Two-step sign-in -------------------------------------------------------------------------


@pytest.mark.django_db
def test_sign_in_needs_the_code_once_two_factor_is_on(client_for, nurse):
    enable_mfa(client_for(nurse), nurse)

    device, response = password_step(nurse.email)
    assert response.status_code == 202
    assert response.json()["mfa_required"] is True
    assert device.get("/api/v1/auth/me/").status_code == 401  # not signed in yet

    wrong = device.post("/api/v1/auth/login/verify/", {"code": "123456"}, format="json")
    assert wrong.status_code == 400
    assert AuditEvent.objects.filter(action=AuditAction.AUTH_MFA_FAILED).count() == 1

    ok = device.post("/api/v1/auth/login/verify/", {"code": code_for(nurse, 1)}, format="json")
    assert ok.status_code == 200
    assert ok.json()["mfa"]["verified"] is True
    assert device.get("/api/v1/auth/me/").status_code == 200
    assert UserSession.objects.filter(user=nurse, ended_at__isnull=True).exists()


@pytest.mark.django_db
def test_a_code_cannot_be_used_twice(client_for, nurse):
    enable_mfa(client_for(nurse), nurse)  # consumed the current step
    device, _ = password_step(nurse.email)
    reused = device.post("/api/v1/auth/login/verify/", {"code": code_for(nurse)}, format="json")
    assert reused.status_code == 400


@pytest.mark.django_db
def test_backup_code_works_once(client_for, nurse):
    codes = enable_mfa(client_for(nurse), nurse)
    device, _ = password_step(nurse.email)
    assert (
        device.post(
            "/api/v1/auth/login/verify/", {"code": codes[0].upper()}, format="json"
        ).status_code
        == 200
    )
    assert AuditEvent.objects.filter(action=AuditAction.AUTH_MFA_RECOVERY_CODE_USED).exists()

    cache.clear()
    second, _ = password_step(nurse.email)
    assert (
        second.post("/api/v1/auth/login/verify/", {"code": codes[0]}, format="json").status_code
        == 400
    )


@pytest.mark.django_db
def test_too_many_wrong_codes_restart_the_sign_in(client_for, nurse):
    enable_mfa(client_for(nurse), nurse)
    device, _ = password_step(nurse.email)
    for _ in range(4):
        assert (
            device.post("/api/v1/auth/login/verify/", {"code": "000000"}, format="json").status_code
            == 400
        )
    cache.clear()  # keep the per-minute rate limit out of this test
    fifth = device.post("/api/v1/auth/login/verify/", {"code": "000000"}, format="json")
    assert fifth.json()["code"] == "MFA_CHALLENGE_EXPIRED"
    right = device.post("/api/v1/auth/login/verify/", {"code": code_for(nurse, 1)}, format="json")
    assert right.json()["code"] == "MFA_CHALLENGE_EXPIRED"  # must start again with the password


@pytest.mark.django_db
def test_code_step_expires_after_five_minutes(client_for, nurse):
    enable_mfa(client_for(nurse), nurse)
    device, _ = password_step(nurse.email)
    session = device.session
    pending = session[mfa.SESSION_PENDING_KEY]
    pending["expires_at"] = (timezone.now() - timedelta(seconds=1)).isoformat()
    session[mfa.SESSION_PENDING_KEY] = pending
    session.save()
    late = device.post("/api/v1/auth/login/verify/", {"code": code_for(nurse, 1)}, format="json")
    assert late.json()["code"] == "MFA_CHALLENGE_EXPIRED"


@pytest.mark.django_db
def test_voluntary_user_can_turn_two_factor_off_with_a_code(client_for, nurse):
    client = client_for(nurse)
    enable_mfa(client, nurse)
    off = client.post("/api/v1/auth/mfa/disable/", {"code": code_for(nurse, 1)}, format="json")
    assert off.status_code == 204
    assert not MfaDevice.objects.filter(user=nurse).exists()
    assert password_step(nurse.email)[1].status_code == 200


# --- Enforcement for privileged users ---------------------------------------------------------


@pytest.mark.django_db
@ENFORCED
def test_privileged_user_must_set_up_two_factor_before_using_the_api(client_for, admin):
    client = client_for(admin)
    blocked = client.get("/api/v1/facilities/")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "MFA_SETUP_REQUIRED"
    me = client.get("/api/v1/auth/me/").json()
    assert me["mfa"] == {
        "enabled": False,
        "required": True,
        "verified": False,
        "recovery_codes_remaining": 0,
    }

    enable_mfa(client, admin)
    assert client.get("/api/v1/facilities/").status_code == 200


@pytest.mark.django_db
@ENFORCED
def test_privileged_user_cannot_turn_two_factor_off(client_for, admin):
    client = client_for(admin)
    enable_mfa(client, admin)
    refused = client.post("/api/v1/auth/mfa/disable/", {"code": code_for(admin, 1)}, format="json")
    assert refused.status_code == 409
    assert refused.json()["code"] == "MFA_REQUIRED_FOR_ROLE"


@pytest.mark.django_db
@ENFORCED
def test_regular_staff_are_not_forced(client_for, nurse):
    assert client_for(nurse).get("/api/v1/facilities/").status_code == 200


@pytest.mark.django_db
@ENFORCED
@override_settings(HIMS_MFA_REQUIRED_FOR_ALL=True)
def test_hospital_can_require_two_factor_for_everyone(client_for, nurse):
    assert client_for(nurse).get("/api/v1/facilities/").json()["code"] == "MFA_SETUP_REQUIRED"


# --- Admin console ----------------------------------------------------------------------------


def admin_login(email, otp_code="") -> tuple[Client, object]:
    console = Client()
    response = console.post(
        "/admin/login/?next=/admin/",
        {"username": email, "password": PASSWORD, "otp_code": otp_code},
    )
    return console, response


@pytest.mark.django_db
@ENFORCED
def test_admin_console_requires_the_code(client_for, admin):
    enable_mfa(client_for(admin), admin)

    _, missing = admin_login(admin.email)
    assert missing.status_code == 200
    assert b"Enter the code from your authenticator app" in missing.content

    cache.clear()
    console, ok = admin_login(admin.email, code_for(admin, 1))
    assert ok.status_code == 302
    assert console.get("/admin/").status_code == 200


@pytest.mark.django_db
@ENFORCED
def test_privileged_admin_without_two_factor_is_sent_to_set_it_up(admin):
    _, response = admin_login(admin.email)
    assert response.status_code == 200
    assert b"requires two-factor sign-in" in response.content

    console = Client()
    console.force_login(admin)  # a session that never passed two-factor
    assert console.get("/admin/").status_code == 302


@pytest.mark.django_db
def test_admin_can_reset_a_lost_phone_but_not_their_own(client_for, admin_user, nurse):
    enable_mfa(client_for(nurse), nurse)
    device, _ = password_step(nurse.email)
    device.post("/api/v1/auth/login/verify/", {"code": code_for(nurse, 1)}, format="json")
    assert device.get("/api/v1/auth/me/").status_code == 200

    console = Client()
    console.force_login(admin_user)
    console.post(
        "/admin/identity/user/",
        {"action": "reset_two_factor", "_selected_action": [str(nurse.pk), str(admin_user.pk)]},
    )
    assert not MfaDevice.objects.filter(user=nurse).exists()
    assert device.get("/api/v1/auth/me/").status_code == 401  # signed out everywhere
    assert (
        AuditEvent.objects.filter(action=AuditAction.AUTH_MFA_RESET, actor_id=admin_user.pk).count()
        == 1
    )


@pytest.mark.django_db
def test_authenticator_secret_is_never_shown_in_the_admin(client_for, admin_user, nurse):
    enable_mfa(client_for(nurse), nurse)
    device = MfaDevice.objects.get(user=nurse)
    console = Client()
    console.force_login(admin_user)
    page = console.get(f"/admin/identity/mfadevice/{device.pk}/change/")
    assert page.status_code == 200
    assert device.secret_encrypted.encode() not in page.content
    assert crypto.decrypt(device.secret_encrypted).encode() not in page.content


# --- Production guard -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("extra_env", "message"),
    [
        ({}, "HIMS_FIELD_ENCRYPTION_KEYS must be set"),
        (
            {"HIMS_FIELD_ENCRYPTION_KEYS": "k", "HIMS_MFA_REQUIRED_FOR_PRIVILEGED": "false"},
            "cannot be disabled in production",
        ),
    ],
)
def test_production_refuses_unsafe_two_factor_configuration(extra_env, message):
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "HIMS_ENV_FILE": "__none__",
        "HIMS_ENVIRONMENT": "production",
        "HIMS_DATABASE_ENVIRONMENT": "production",
        "HIMS_DEPLOYMENT_ID": "guard-test",
        "DJANGO_SECRET_KEY": "x" * 50,
        "DATABASE_URL": "postgres://u:p@db.invalid:5432/h",
        **extra_env,
    }
    if "HIMS_FIELD_ENCRYPTION_KEYS" not in extra_env:
        env.pop("HIMS_FIELD_ENCRYPTION_KEYS", None)
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert message in result.stderr
