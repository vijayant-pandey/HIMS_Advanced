"""The admin console answers only allowed addresses (HIMS-SEC-015; spec 13.1, 13.4; ADR-016).

Anyone else gets the same "Not found" as when the console is switched off, before sign-in, with
a correct password or with a session taken from someone allowed. Refusals are counted per day
and address, and audited once (again if a signed-in session shows up from that address).
"""

import os
import subprocess
import sys

import pytest
from django.core.cache import cache
from django.test import Client, override_settings

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.compliance import console_access
from apps.compliance.models import ConsoleAccessBlock
from common.client_ip import console_allows, validate_console_networks
from common.tests.test_static_files import BACKEND, PRODUCTION_ENV, _setting_in

PASSWORD = "Synthetic-Allowlist-Passw0rd-1015"
OUTSIDE = "203.0.113.9"  # a documentation address: never a real person


@pytest.fixture(autouse=True)
def _clear_lockouts():
    cache.clear()


def _refusals(**filters):
    return AuditEvent.objects.filter(action=AuditAction.AUTH_CONSOLE_ADDRESS_REFUSED, **filters)


@pytest.mark.django_db
def test_this_computer_reaches_the_console_and_others_get_not_found(organization):
    client = Client()
    assert client.get("/admin/login/").status_code == 200
    refused = client.get("/admin/login/", REMOTE_ADDR=OUTSIDE)
    missing = client.get("/no-such-page/", REMOTE_ADDR=OUTSIDE)
    assert refused.status_code == 404
    assert refused.content == missing.content  # nothing says a console is here
    # Without the slash it is not redirected to the console either.
    assert client.get("/admin", REMOTE_ADDR=OUTSIDE).status_code == 404


@pytest.mark.django_db
def test_a_correct_password_from_elsewhere_signs_nobody_in(make_user, system_roles):
    user = make_user(role=system_roles["organization-administrator"], password=PASSWORD)
    client = Client()
    response = client.post(
        "/admin/login/", {"username": user.email, "password": PASSWORD}, REMOTE_ADDR=OUTSIDE
    )
    assert response.status_code == 404
    assert "_auth_user_id" not in client.session
    assert not AuditEvent.objects.filter(action=AuditAction.AUTH_LOGIN).exists()


@pytest.mark.django_db
def test_a_session_used_from_elsewhere_is_refused_and_named(admin_user):
    client = Client()
    client.force_login(admin_user)
    assert client.get("/admin/").status_code == 200
    assert client.get("/admin/", REMOTE_ADDR=OUTSIDE).status_code == 404
    block = ConsoleAccessBlock.objects.get(ip_address=OUTSIDE)
    assert block.signed_in_user == admin_user
    event = _refusals().get()
    assert event.actor_id == admin_user.pk
    assert event.outcome == AuditEvent.Outcome.DENIED
    assert event.metadata == {"page": "/admin/", "signed_in": True}


@pytest.mark.django_db
def test_refusals_are_added_up_per_day_and_audited_once(admin_user, organization):
    client = Client()
    for _ in range(3):
        client.get("/admin/login/", REMOTE_ADDR=OUTSIDE)
    block = ConsoleAccessBlock.objects.get()
    assert (block.attempts, block.signed_in_user, block.last_path) == (3, None, "/admin/login/")
    assert _refusals().count() == 1
    # The first signed-in session from that address is audited again: it may be stolen.
    client.force_login(admin_user)
    client.get("/admin/staff/staffmember/", REMOTE_ADDR=OUTSIDE)
    client.get("/admin/staff/staffmember/", REMOTE_ADDR=OUTSIDE)
    block.refresh_from_db()
    assert (block.attempts, block.signed_in_user) == (5, admin_user)
    assert _refusals().count() == 2


@pytest.mark.django_db
def test_ids_are_removed_from_the_recorded_page(organization):
    page = "/admin/staff/staffmember/0b0f6f3e-2c55-4b59-9d8e-1f2a3b4c5d6e/change/"
    Client().get(page, REMOTE_ADDR=OUTSIDE)
    assert ConsoleAccessBlock.objects.get().last_path == "/admin/staff/staffmember/{id}/change/"


@pytest.mark.django_db
def test_knocking_from_many_addresses_cannot_fill_the_database(organization, monkeypatch):
    monkeypatch.setattr(console_access, "MAX_ROWS_PER_DAY", 2)
    client = Client()
    for n in range(1, 5):
        assert client.get("/admin/", REMOTE_ADDR=f"198.51.100.{n}").status_code == 404
    assert ConsoleAccessBlock.objects.count() == 2


@pytest.mark.django_db
def test_the_rest_of_hims_is_not_affected(organization):
    client = Client()
    assert client.get("/health/live/", REMOTE_ADDR=OUTSIDE).status_code == 200
    assert client.get("/api/v1/auth/me/", REMOTE_ADDR=OUTSIDE).status_code in (401, 403)
    assert not ConsoleAccessBlock.objects.exists()


@pytest.mark.django_db
@override_settings(HIMS_ENABLE_ADMIN=False)
def test_nothing_is_counted_when_the_console_is_off(organization):
    Client().get("/admin/", REMOTE_ADDR=OUTSIDE)
    assert not ConsoleAccessBlock.objects.exists()


@pytest.mark.django_db
@override_settings(
    HIMS_TRUSTED_PROXIES=["10.0.0.0/8"], HIMS_ADMIN_ALLOWED_NETWORKS=["192.0.2.0/24", "10.0.0.0/8"]
)
def test_behind_the_load_balancer_the_real_address_decides(organization):
    client = Client()

    def via_proxy(forwarded=None):
        extra = {"HTTP_X_FORWARDED_FOR": forwarded} if forwarded else {}
        return client.get("/admin/login/", REMOTE_ADDR="10.0.0.5", **extra).status_code

    assert via_proxy("192.0.2.7") == 200
    assert via_proxy("198.51.100.1") == 404
    # A made-up header from the sender does not help: the proxy's own entry is the real one.
    assert via_proxy("192.0.2.7, 198.51.100.1") == 404
    # Our own proxy is never enough, even when its network is listed: the sender is unknown.
    assert via_proxy() == 404


@override_settings(HIMS_TRUSTED_PROXIES=[], HIMS_ADMIN_ALLOWED_NETWORKS=["127.0.0.1", "::1"])
def test_address_matching():
    assert console_allows("127.0.0.1")
    assert console_allows("::ffff:127.0.0.1")  # IPv4 seen through IPv6
    assert console_allows("::1")
    assert not console_allows("127.0.0.2")
    assert not console_allows(None)
    assert not console_allows("not-an-address")


@pytest.mark.parametrize("entry", ["0.0.0.0/0", "::/0", "not-a-network"])
def test_a_list_that_lets_everyone_in_or_cannot_be_read_is_refused(entry):
    with pytest.raises(ValueError):
        validate_console_networks(["10.8.0.0/16", entry])


def _start_fails(extra_env: dict) -> str:
    env = {
        **{k: v for k, v in os.environ.items() if not k.endswith("DATABASE_URL")},
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "HIMS_ENV_FILE": "__no_env_file__",
        **PRODUCTION_ENV,
        **extra_env,
    }
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    return result.stderr


def test_hosted_console_needs_a_list_that_does_not_let_everyone_in():
    assert "HIMS_ADMIN_ALLOWED_NETWORKS must list" in _start_fails({"HIMS_ENABLE_ADMIN": "true"})
    stderr = _start_fails({"HIMS_ENABLE_ADMIN": "true", "HIMS_ADMIN_ALLOWED_NETWORKS": "0.0.0.0/0"})
    assert "would let every address in" in stderr
    allowed = _setting_in(
        "config.settings.production",
        "settings.HIMS_ADMIN_ALLOWED_NETWORKS",
        {
            **PRODUCTION_ENV,
            "HIMS_ENABLE_ADMIN": "true",
            "HIMS_ADMIN_ALLOWED_NETWORKS": "10.8.0.0/16",
        },
    )
    assert allowed == "['10.8.0.0/16']"
    # With the console off (the hosted default) no list is needed.
    enabled = _setting_in(
        "config.settings.production", "settings.HIMS_ENABLE_ADMIN", PRODUCTION_ENV
    )
    assert enabled == "False"
