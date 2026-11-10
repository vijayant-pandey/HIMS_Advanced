"""Passkeys as a second factor (HIMS-IAM-014; spec 13.1). A software authenticator stands in for a
phone or security key: it holds a real key pair and signs exactly as a device does. All data is
synthetic."""

import hashlib
import json
import os

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.cache import cache
from rest_framework.test import APIClient
from webauthn.helpers import bytes_to_base64url

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.identity import confirmation, mfa
from apps.identity.models import Passkey
from apps.identity.passkeys import MAX_PASSKEYS
from apps.identity.tests.test_mfa import PASSWORD, code_for, enable_mfa, password_step
from common.admin.tests.test_console_additions import console

API = "/api/v1/auth"
ORIGIN = "http://app.test"


class SoftAuthenticator:
    """A device with one passkey: ES256 key, "none" attestation, a signature counter."""

    def __init__(self, rp_id="app.test"):
        self.rp_id = rp_id
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(16)
        self.count = 0

    def _cose_key(self) -> bytes:
        numbers = self.key.public_key().public_numbers()
        return cbor2.dumps(
            {
                1: 2,
                3: -7,
                -1: 1,
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    def _client_data(self, kind, options, origin) -> bytes:
        return json.dumps(
            {
                "type": kind,
                "challenge": options["challenge"],
                "origin": origin,
                "crossOrigin": False,
            }
        ).encode()

    def create(self, options: dict, *, origin=ORIGIN) -> dict:
        client_data = self._client_data("webauthn.create", options, origin)
        auth_data = (
            hashlib.sha256(self.rp_id.encode()).digest()
            + bytes([0x45])  # user present, user verified, credential included
            + self.count.to_bytes(4, "big")
            + bytes(16)  # no maker identity
            + len(self.credential_id).to_bytes(2, "big")
            + self.credential_id
            + self._cose_key()
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": bytes_to_base64url(self.credential_id),
            "rawId": bytes_to_base64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "attestationObject": bytes_to_base64url(attestation),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
        }

    def get(self, options: dict, *, origin=ORIGIN, counter=None, signer=None) -> dict:
        self.count = self.count + 1 if counter is None else counter
        client_data = self._client_data("webauthn.get", options, origin)
        auth_data = (
            hashlib.sha256(self.rp_id.encode()).digest()
            + bytes([0x05])  # user present, user verified
            + self.count.to_bytes(4, "big")
        )
        signature = (signer or self.key).sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": bytes_to_base64url(self.credential_id),
            "rawId": bytes_to_base64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "authenticatorData": bytes_to_base64url(auth_data),
                "signature": bytes_to_base64url(signature),
            },
            "clientExtensionResults": {},
        }


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    cache.clear()


@pytest.fixture
def admin(make_user, system_roles):
    return make_user(role=system_roles["organization-administrator"], password=PASSWORD)


@pytest.fixture
def signed_in(client_for, admin):
    """The administrator, signed in with two-factor on (signing in counts as confirming)."""
    client = client_for(admin)
    enable_mfa(client, admin)
    return client


def add_passkey(client, device=None, name="Work laptop"):
    device = device or SoftAuthenticator()
    options = client.post(f"{API}/passkeys/add-options/").json()["public_key"]
    response = client.post(
        f"{API}/passkeys/add/", {"name": name, "credential": device.create(options)}, format="json"
    )
    return device, response


def passkey_sign_in(email, device, **sign):
    cache.clear()  # many sign-ins in a row here; the rate limit is tested elsewhere
    client, first = password_step(email)
    options = client.post(f"{API}/login/passkey-options/").json()["public_key"]
    response = client.post(
        f"{API}/login/passkey/", {"credential": device.get(options, **sign)}, format="json"
    )
    return client, first, response


# --- Adding --------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_add_a_passkey_only_its_public_key_is_kept(signed_in, admin):
    options = signed_in.post(f"{API}/passkeys/add-options/").json()["public_key"]
    assert options["rp"]["id"] == "app.test"
    assert options["user"]["name"] == admin.email
    assert options["attestation"] == "none"
    device, response = add_passkey(signed_in)
    assert response.status_code == 201, response.content
    assert response.json()["name"] == "Work laptop"
    passkey = Passkey.objects.get(user=admin)
    assert passkey.credential_id == bytes_to_base64url(device.credential_id)
    assert passkey.transports == ["internal"]
    listed = signed_in.get(f"{API}/passkeys/").json()
    assert [row["name"] for row in listed] == ["Work laptop"]
    assert "public_key" not in listed[0] and "credential_id" not in listed[0]
    assert signed_in.get(f"{API}/mfa/").json()["passkeys"] == 1
    assert AuditEvent.objects.filter(action=AuditAction.AUTH_PASSKEY_ADDED).count() == 1


@pytest.mark.django_db
def test_a_passkey_is_added_to_the_authenticator_app_not_instead(client_for, admin):
    response = client_for(admin).post(f"{API}/passkeys/add-options/")
    assert response.status_code == 409 and response.json()["code"] == "MFA_NOT_ENABLED"


@pytest.mark.django_db
def test_adding_asks_to_confirm_it_is_you(signed_in):
    session = signed_in.session
    session[confirmation.SESSION_CONFIRMED_KEY] = 0
    session.save()
    response = signed_in.post(f"{API}/passkeys/add-options/")
    assert response.status_code == 403 and response.json()["code"] == "REAUTH_REQUIRED"


@pytest.mark.django_db
def test_a_passkey_for_another_site_or_challenge_is_refused(signed_in):
    options = signed_in.post(f"{API}/passkeys/add-options/").json()["public_key"]
    fake_site = SoftAuthenticator().create(options, origin="https://phishing.example")
    response = signed_in.post(
        f"{API}/passkeys/add/", {"name": "x", "credential": fake_site}, format="json"
    )
    assert response.status_code == 400 and response.json()["code"] == "PASSKEY_NOT_ACCEPTED"
    # The challenge is used once: even a correct answer to it is now refused.
    again = signed_in.post(
        f"{API}/passkeys/add/",
        {"name": "x", "credential": SoftAuthenticator().create(options)},
        format="json",
    )
    assert again.status_code == 400
    other_device = SoftAuthenticator(rp_id="phishing.example")
    _, wrong_rp = add_passkey(signed_in, other_device)
    assert wrong_rp.status_code == 400
    assert not Passkey.objects.exists()


@pytest.mark.django_db
def test_the_same_passkey_twice_and_the_limit(signed_in, admin):
    device, _ = add_passkey(signed_in)
    _, twice = add_passkey(signed_in, device)
    assert twice.status_code in (400, 409)
    for n in range(MAX_PASSKEYS - 1):
        assert add_passkey(signed_in, name=f"Key {n}")[1].status_code == 201
    over = signed_in.post(f"{API}/passkeys/add-options/")
    assert over.status_code == 409 and over.json()["code"] == "TOO_MANY_PASSKEYS"


# --- Signing in ----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_sign_in_with_a_passkey_instead_of_the_code(signed_in, admin):
    device, _ = add_passkey(signed_in)
    client, first, response = passkey_sign_in(admin.email, device)
    assert first.status_code == 202 and first.json()["passkey_available"] is True
    assert response.status_code == 200, response.content
    assert client.get(f"{API}/me/").json()["mfa"]["verified"] is True
    event = AuditEvent.objects.filter(action=AuditAction.AUTH_MFA_VERIFIED).latest("occurred_at")
    assert event.metadata["method"] == "passkey"
    login = AuditEvent.objects.filter(action=AuditAction.AUTH_LOGIN).latest("occurred_at")
    assert login.metadata["via"] == "password+passkey"
    assert Passkey.objects.get().last_used_at is not None


@pytest.mark.django_db
def test_the_code_still_works_alongside(signed_in, admin):
    add_passkey(signed_in)
    client, first = password_step(admin.email)
    response = client.post(
        f"{API}/login/verify/", {"code": code_for(admin, step_offset=1)}, format="json"
    )
    assert first.json()["passkey_available"] is True and response.status_code == 200


@pytest.mark.django_db
def test_without_a_passkey_sign_in_says_so(signed_in, admin):
    client, first = password_step(admin.email)
    assert first.json()["passkey_available"] is False
    response = client.post(f"{API}/login/passkey-options/")
    assert response.status_code == 409 and response.json()["code"] == "NO_PASSKEY"


@pytest.mark.django_db
def test_no_passkey_step_without_the_password_first(signed_in, admin):
    add_passkey(signed_in)
    response = APIClient().post(f"{API}/login/passkey-options/")
    assert response.status_code == 400 and response.json()["code"] == "MFA_CHALLENGE_EXPIRED"


@pytest.mark.django_db
def test_a_wrong_signature_or_a_copied_key_is_refused_and_counted(signed_in, admin):
    device, _ = add_passkey(signed_in)
    stranger = ec.generate_private_key(ec.SECP256R1())
    _, _, forged = passkey_sign_in(admin.email, device, signer=stranger)
    assert forged.status_code == 400 and forged.json()["code"] == "PASSKEY_NOT_ACCEPTED"
    _, _, ok = passkey_sign_in(admin.email, device, counter=5)
    assert ok.status_code == 200
    # A copy of the key replays an old counter value: refused.
    _, _, copied = passkey_sign_in(admin.email, device, counter=3)
    assert copied.status_code == 400
    failures = AuditEvent.objects.filter(action=AuditAction.AUTH_MFA_FAILED)
    assert failures.count() == 2 and failures.first().metadata["method"] == "passkey"


@pytest.mark.django_db
def test_five_wrong_tries_end_the_sign_in(signed_in, admin):
    device, _ = add_passkey(signed_in)
    client, _ = password_step(admin.email)
    stranger = ec.generate_private_key(ec.SECP256R1())
    for _ in range(mfa.CHALLENGE_MAX_ATTEMPTS):
        cache.clear()  # the rate limit is not what is tested here
        options = client.post(f"{API}/login/passkey-options/").json()["public_key"]
        last = client.post(
            f"{API}/login/passkey/",
            {"credential": device.get(options, signer=stranger)},
            format="json",
        )
    assert last.json()["code"] == "MFA_CHALLENGE_EXPIRED"
    assert client.post(f"{API}/login/passkey-options/").json()["code"] == "MFA_CHALLENGE_EXPIRED"


@pytest.mark.django_db
def test_someone_elses_passkey_does_not_sign_you_in(signed_in, admin, make_user, system_roles):
    other = make_user(role=system_roles["organization-administrator"], password=PASSWORD)
    other_client = APIClient()
    other_client.force_login(other)
    enable_mfa(other_client, other)
    theirs, _ = add_passkey(other_client)
    add_passkey(signed_in)
    _, _, response = passkey_sign_in(admin.email, theirs)
    assert response.status_code == 400


# --- Confirm it's you ----------------------------------------------------------------------------


@pytest.mark.django_db
def test_confirm_it_is_you_with_a_passkey(signed_in):
    device, _ = add_passkey(signed_in)
    session = signed_in.session
    session[confirmation.SESSION_CONFIRMED_KEY] = 0
    session.save()
    assert signed_in.get(f"{API}/confirm-identity/").json()["passkey_available"] is True
    options = signed_in.post(f"{API}/confirm-identity/passkey-options/").json()["public_key"]
    response = signed_in.post(
        f"{API}/confirm-identity/",
        {"password": PASSWORD, "passkey": device.get(options)},
        format="json",
    )
    assert response.status_code == 200 and response.json()["confirmed"] is True
    event = AuditEvent.objects.filter(action=AuditAction.AUTH_IDENTITY_CONFIRMED).latest(
        "occurred_at"
    )
    assert event.metadata["method"] == "password+passkey"


@pytest.mark.django_db
def test_a_passkey_does_not_replace_the_password(signed_in):
    device, _ = add_passkey(signed_in)
    options = signed_in.post(f"{API}/confirm-identity/passkey-options/").json()["public_key"]
    response = signed_in.post(
        f"{API}/confirm-identity/",
        {"password": "Synthetic-Wrong-Passw0rd-2027", "passkey": device.get(options)},
        format="json",
    )
    assert response.status_code == 400 and response.json()["code"] == "REAUTH_FAILED"


@pytest.mark.django_db
def test_a_sign_in_challenge_cannot_be_used_to_confirm(signed_in, admin):
    device, _ = add_passkey(signed_in)
    client, _ = password_step(admin.email)
    options = client.post(f"{API}/login/passkey-options/").json()["public_key"]
    response = signed_in.post(
        f"{API}/confirm-identity/",
        {"password": PASSWORD, "passkey": device.get(options)},
        format="json",
    )
    assert response.status_code == 400


# --- Removing ------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_remove_your_own_passkey_only(signed_in, admin, make_user):
    add_passkey(signed_in)
    passkey = Passkey.objects.get()
    stranger = APIClient()
    stranger.force_login(make_user())
    assert stranger.post(f"{API}/passkeys/{passkey.pk}/remove/").status_code == 409
    assert signed_in.post(f"{API}/passkeys/{passkey.pk}/remove/").status_code == 204
    assert not Passkey.objects.exists()
    event = AuditEvent.objects.get(action=AuditAction.AUTH_PASSKEY_REMOVED)
    assert event.metadata["by_owner"] is True


@pytest.mark.django_db
def test_switching_two_factor_off_or_a_reset_removes_passkeys(
    signed_in, admin, client_for, make_user, system_roles
):
    add_passkey(signed_in)
    other_admin = make_user(role=system_roles["organization-administrator"], password=PASSWORD)
    mfa.admin_reset(user=admin, actor=other_admin)
    assert not Passkey.objects.exists()


@pytest.mark.django_db
def test_console_lists_passkeys_without_keys_and_removes_a_lost_one(
    signed_in, admin, make_user, system_roles
):
    add_passkey(signed_in)
    other_admin = make_user(role=system_roles["organization-administrator"], password=PASSWORD)
    client = console(other_admin, confirmed=True)
    page = client.get("/admin/identity/passkey/").content.decode()
    assert "Work laptop" in page
    passkey = Passkey.objects.get()
    detail = client.get(f"/admin/identity/passkey/{passkey.pk}/change/").content.decode()
    assert passkey.credential_id not in detail
    client.post(
        "/admin/identity/passkey/",
        {"action": "remove_selected", "_selected_action": [str(passkey.pk)]},
    )
    assert not Passkey.objects.exists()
    event = AuditEvent.objects.get(action=AuditAction.AUTH_PASSKEY_REMOVED)
    assert event.actor_id == other_admin.pk and event.metadata["by_owner"] is False


@pytest.mark.django_db
def test_console_removal_asks_to_confirm_it_is_you(signed_in, admin, make_user, system_roles):
    add_passkey(signed_in)
    other_admin = make_user(role=system_roles["organization-administrator"], password=PASSWORD)
    client = console(other_admin, confirmed=False)
    passkey = Passkey.objects.get()
    response = client.post(
        "/admin/identity/passkey/",
        {"action": "remove_selected", "_selected_action": [str(passkey.pk)]},
    )
    assert response.status_code == 302 and "confirm" in response["Location"]
    assert Passkey.objects.exists()
