"""Hosting readiness (spec 17, 30, 31; HIMS-OPS-020). All data is synthetic."""

from datetime import timedelta

import pytest
from django.core.management import CommandError, call_command
from django.test import Client, override_settings
from django.utils import timezone

from apps.audit.integrity import seal_pending_events
from apps.audit.models import AuditEvent
from apps.compliance import hosting

# What a correctly set-up hosted environment has (values are made up for the test).
HOSTED = {
    "DEBUG": False,
    "SECURE_SSL_REDIRECT": True,
    "SESSION_COOKIE_SECURE": True,
    "SECURE_HSTS_SECONDS": 31_536_000,
    "ALLOWED_HOSTS": ["hims-dev.example.test"],
    "SECRET_KEY": "synthetic-" + "x" * 60,
    "HIMS_FIELD_ENCRYPTION_KEYS": ["synthetic-field-key"],
    "HIMS_AUDIT_CHAIN_KEYS": ["ci:" + "y" * 40],
    "HIMS_TRUSTED_PROXIES": ["10.0.0.0/8"],
    "HIMS_ADMIN_ALLOWED_NETWORKS": ["192.0.2.0/24"],
}


def _by_key() -> dict[str, dict]:
    return {check["key"]: check for check in hosting.checks()}


def _late_event():
    return AuditEvent.objects.create(
        occurred_at=timezone.now() - timedelta(minutes=hosting.SEAL_LATE_MINUTES + 5),
        actor_type=AuditEvent.ActorType.SYSTEM,
        action="organization.updated",
        resource_type="organization",
        outcome=AuditEvent.Outcome.SUCCESS,
    )


@pytest.mark.django_db
def test_every_check_says_what_to_do_when_it_is_not_met():
    for check in hosting.checks():
        assert check["status"] in hosting.STATUSES
        assert check["label"] and check["spec"] and check["detail"]
        assert bool(check["fix"]) == (check["status"] != hosting.OK), check["key"]


@pytest.mark.django_db
def test_a_hosted_environment_is_fit_for_test_data_but_not_yet_for_real_data():
    with override_settings(**HOSTED):
        result = hosting.readiness()
    failing = [check["key"] for check in result["checks"] if check["status"] == hosting.FAIL]
    assert failing == []
    assert result["ready_to_host"] is True
    # A free host cannot give these yet: they are needed before real patient data.
    warned = {check["key"] for check in result["checks"] if check["status"] == hosting.WARN}
    assert {"documents", "virus_scanner", "backups"} <= warned
    assert result["ready_for_real_data"] is False


@pytest.mark.django_db
def test_missing_scheduler_is_noticed_from_the_audit_log():
    _late_event()
    assert _by_key()["scheduled_jobs"]["status"] == hosting.FAIL
    seal_pending_events()
    assert _by_key()["scheduled_jobs"]["status"] == hosting.OK


@pytest.mark.django_db
def test_unsafe_settings_must_be_fixed_before_going_online():
    unsafe = {
        **HOSTED,
        "DEBUG": True,
        "ALLOWED_HOSTS": ["*"],
        "HIMS_TRUSTED_PROXIES": [],
        "HIMS_ENABLE_ADMIN": True,
        "HIMS_ADMIN_ALLOWED_NETWORKS": ["0.0.0.0/0"],
        "HIMS_FIELD_ENCRYPTION_KEYS": [],
    }
    with override_settings(**unsafe):
        checks = _by_key()
    for key in ("debug", "allowed_hosts", "trusted_proxies", "admin_console", "keys"):
        assert checks[key]["status"] == hosting.FAIL, key


@pytest.mark.django_db
def test_command_fails_on_must_fix_and_optionally_on_before_real_data(capsys):
    with pytest.raises(CommandError):
        call_command("hosting_check")  # this test environment is not a hosted one
    with override_settings(**HOSTED):
        call_command("hosting_check")
        assert "needed before real patient data" in capsys.readouterr().out
        with pytest.raises(CommandError):
            call_command("hosting_check", "--real-data")


@pytest.mark.django_db
def test_hosting_tab_and_console(client_for, auditor_user, admin_user, make_user):
    body = client_for(auditor_user).get("/api/v1/security/hosting/").json()
    assert body["environment"] == "test"
    assert {check["key"] for check in body["checks"]} == set(_by_key())
    assert client_for(make_user()).get("/api/v1/security/hosting/").status_code == 403

    console = Client()
    console.force_login(admin_user)
    page = console.get("/admin/compliance/consoleaccessblock/security-status/").content.decode()
    assert "Hosting readiness" in page
