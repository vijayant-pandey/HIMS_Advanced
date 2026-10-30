"""Tamper evidence for the audit log (HIMS-SEC-010, spec 13.4). All data is synthetic.

Tampering is simulated the way an attacker with database access would do it: by switching the
append-only triggers off for a moment. The test transaction rolls this back afterwards.
"""

import itertools
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from django.core import mail
from django.core.management import CommandError, call_command
from django.db import DatabaseError, connection, transaction
from django.test import Client, override_settings
from django.utils import timezone

from apps.audit.integrity import (
    GENESIS,
    run_integrity_check,
    seal_pending_events,
)
from apps.audit.models import AuditChainEntry, AuditEvent, AuditIntegrityCheck
from apps.audit.services import AuditAction, record_audit_event

API = "/api/v1/audit-integrity-checks"
SCHEDULED = AuditIntegrityCheck.Trigger.SCHEDULED
KEY_A = "k1:" + "a" * 64
KEY_B = "k2:" + "b" * 64


def _events(count=3):
    return [
        record_audit_event(
            action=AuditAction.FACILITY_UPDATED,
            resource_type="facility",
            resource_id=str(n),
            changes={"before": {"phone": ""}, "after": {"phone": f"+91 {n}", "beds": n}},
            metadata={"nested": {"list": [1, 2.5, "x"]}},
        )
        for n in range(count)
    ]


def _sql(statement, params=()):
    with connection.cursor() as cursor:
        cursor.execute(statement, params)


def _without_triggers(*statements):
    """Run raw SQL with every trigger (append-only protection included) switched off, as a
    database superuser could."""
    _sql("SET CONSTRAINTS ALL IMMEDIATE")
    _sql("SET session_replication_role = replica")
    try:
        for statement, params in statements:
            _sql(statement, params)
    finally:
        _sql("SET session_replication_role = DEFAULT")


def _kinds(check):
    return {problem["kind"] for problem in check.problems}


@pytest.fixture
def sealed(organization):
    events = _events()
    seal_pending_events()
    return events


@pytest.mark.django_db
def test_events_are_sealed_once_in_a_linked_chain(organization):
    _events(3)
    assert seal_pending_events() >= 3
    assert seal_pending_events() == 0  # nothing new: safe to run any number of times
    links = list(AuditChainEntry.objects.order_by("sequence"))
    assert [link.sequence for link in links] == list(range(1, len(links) + 1))
    assert links[0].previous_hash == GENESIS
    for before, after in itertools.pairwise(links):
        assert after.previous_hash == before.entry_hash
    assert {link.key_id for link in links} == {"local"}


@pytest.mark.django_db
def test_sealing_works_in_batches_for_existing_history(organization):
    _events(7)
    assert seal_pending_events(batch_size=2) == AuditEvent.objects.count()
    assert not AuditEvent.objects.filter(chain_entry__isnull=True).exists()


@pytest.mark.django_db
def test_untouched_log_passes(sealed):
    check = run_integrity_check(trigger=SCHEDULED)
    assert check.outcome == "passed"
    assert check.problem_count == 0
    assert check.entries_checked == AuditChainEntry.objects.count()
    last = AuditChainEntry.objects.order_by("-sequence").first()
    assert (check.last_sequence, check.chain_head) == (last.sequence, last.entry_hash)
    # The check is itself in the audit log (and is sealed by the next run).
    event = AuditEvent.objects.get(action=AuditAction.AUDIT_INTEGRITY_CHECKED)
    assert event.outcome == "success"
    assert event.metadata["chain_head"] == check.chain_head
    assert run_integrity_check(trigger=SCHEDULED).outcome == "passed"


@pytest.mark.django_db
def test_changed_event_is_found(sealed):
    target = sealed[1]
    _without_triggers(
        ("UPDATE audit_events SET reason = 'nothing to see' WHERE id = %s", [target.pk])
    )
    check = run_integrity_check(trigger=SCHEDULED)
    assert check.outcome == "failed"
    problem = next(p for p in check.problems if p["kind"] == "event_changed")
    assert problem["event_id"] == str(target.pk)
    assert problem["sequence"] == target.chain_entry.sequence
    assert AuditEvent.objects.get(action=AuditAction.AUDIT_INTEGRITY_CHECKED).outcome == "failure"


@pytest.mark.django_db
def test_deleted_event_is_found(sealed):
    target = sealed[1]
    sequence = target.chain_entry.sequence
    _without_triggers(
        ("DELETE FROM audit_chain_entries WHERE event_id = %s", [target.pk]),
        ("DELETE FROM audit_events WHERE id = %s", [target.pk]),
    )
    check = run_integrity_check(trigger=SCHEDULED)
    problem = next(p for p in check.problems if p["kind"] == "links_missing")
    assert (problem["sequence"], problem["last_missing"]) == (sequence, sequence)


@pytest.mark.django_db
def test_link_rebuilt_without_the_key_is_found(sealed):
    # An attacker recomputes a fingerprint after changing the event, but cannot sign the link.
    target = sealed[0]
    _without_triggers(
        ("UPDATE audit_events SET reason = 'edited' WHERE id = %s", [target.pk]),
        (
            "UPDATE audit_chain_entries SET event_hash = %s WHERE event_id = %s",
            ["f" * 64, target.pk],
        ),
    )
    assert {"link_changed", "event_changed"} <= _kinds(run_integrity_check(trigger=SCHEDULED))


@pytest.mark.django_db
def test_cutting_off_the_newest_links_is_found(sealed):
    first = run_integrity_check(trigger=SCHEDULED)
    assert first.outcome == "passed"
    newest = AuditChainEntry.objects.filter(sequence__gt=first.last_sequence - 2)
    removed = [str(pk) for pk in newest.values_list("event_id", flat=True)]
    _without_triggers(
        ("DELETE FROM audit_chain_entries WHERE sequence > %s", [first.last_sequence - 2]),
        ("DELETE FROM audit_events WHERE id = ANY(%s::uuid[])", [removed]),
    )
    check = run_integrity_check(trigger=SCHEDULED)
    assert "chain_cut" in _kinds(check)


@pytest.mark.django_db
def test_back_dated_event_that_was_never_sealed_is_found(sealed):
    run_integrity_check(trigger=SCHEDULED)
    slipped_in = AuditEvent.objects.create(
        occurred_at=timezone.now() - timedelta(days=3),
        actor_type=AuditEvent.ActorType.SYSTEM,
        action=AuditAction.ROLE_ASSIGNED,
        resource_type="role_assignment",
        outcome=AuditEvent.Outcome.SUCCESS,
    )
    check = run_integrity_check(trigger=SCHEDULED)
    assert check.unsealed_overdue == 1
    problem = next(p for p in check.problems if p["kind"] == "not_sealed")
    assert problem["event_id"] == str(slipped_in.pk)


@pytest.mark.django_db
def test_keys_can_be_rotated_but_an_unknown_key_is_reported(organization):
    with override_settings(HIMS_AUDIT_CHAIN_KEYS=[KEY_A]):
        _events(2)
        seal_pending_events()
    with override_settings(HIMS_AUDIT_CHAIN_KEYS=[KEY_B, KEY_A]):
        _events(2)
        check = run_integrity_check(trigger=SCHEDULED)
        assert check.outcome == "passed", check.problems
        assert {"k1", "k2"} <= set(AuditChainEntry.objects.values_list("key_id", flat=True))
    with override_settings(HIMS_AUDIT_CHAIN_KEYS=[KEY_B]):
        check = run_integrity_check(trigger=SCHEDULED)
    problem = next(p for p in check.problems if p["kind"] == "unknown_key")
    assert problem["key_id"] == "k1"


@pytest.mark.django_db
def test_chain_tables_are_append_only(sealed):
    run_integrity_check(trigger=SCHEDULED)
    link = AuditChainEntry.objects.first()
    with pytest.raises(RuntimeError):
        link.save()
    with pytest.raises(RuntimeError):
        link.delete()
    for statement in (
        "UPDATE audit_chain_entries SET key_id = 'x'",
        "DELETE FROM audit_chain_entries",
        "UPDATE audit_integrity_checks SET outcome = 'passed'",
        "DELETE FROM audit_integrity_checks",
    ):
        with (
            pytest.raises(DatabaseError, match="append-only"),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(statement)


@pytest.mark.django_db
def test_failed_check_emails_auditors(sealed, auditor_user, admin_user):
    _without_triggers(("UPDATE audit_events SET reason = 'x' WHERE id = %s", [sealed[0].pk]))
    check = run_integrity_check(trigger=SCHEDULED)
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == [auditor_user.email]  # administrators are not auditors
    assert f"/audit/integrity/{check.pk}" in message.body
    assert AuditEvent.objects.filter(action=AuditAction.AUDIT_INTEGRITY_ALERT_SENT).exists()


@pytest.mark.django_db
def test_passed_check_sends_no_email(sealed, auditor_user):
    run_integrity_check(trigger=SCHEDULED)
    assert mail.outbox == []


# --- API ----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_auditor_checks_now_and_sees_history(sealed, client_for, auditor_user):
    client = client_for(auditor_user)
    status = client.get(API + "/status/").json()
    assert status["last_check"] is None
    assert status["waiting_to_be_sealed"] >= 1  # the auditor's own sign-in setup events
    assert status["key_id"] == "local"

    response = client.post(API + "/")
    assert response.status_code == 201
    body = response.json()
    assert body["outcome"] == "passed"
    assert body["trigger"] == "on_demand"
    assert body["requested_by_name"] == auditor_user.display_name
    assert body["problems"] == []
    event = AuditEvent.objects.get(action=AuditAction.AUDIT_INTEGRITY_CHECKED)
    assert event.actor_id == auditor_user.pk

    status = client.get(API + "/status/").json()
    assert status["last_check"]["id"] == body["id"]
    assert status["sealed_events"] == body["last_sequence"]
    assert [row["id"] for row in client.get(API + "/").json()] == [body["id"]]


@pytest.mark.django_db
def test_problem_details_have_plain_words(client_for, auditor_user, sealed):
    _without_triggers(("UPDATE audit_events SET reason = 'x' WHERE id = %s", [sealed[0].pk]))
    check = run_integrity_check(trigger=SCHEDULED)
    body = client_for(auditor_user).get(f"{API}/{check.pk}/").json()
    assert body["outcome"] == "failed"
    problem = body["problems"][0]
    assert problem["kind"] == "event_changed"
    assert problem["action_label"] == "Facility changed"
    assert "changed after it was sealed" in problem["text"]


@pytest.mark.django_db
def test_administrators_cannot_see_or_run_checks(client_for, admin_user):
    client = client_for(admin_user)
    assert client.get(API + "/status/").status_code == 403
    assert client.post(API + "/").status_code == 403
    assert not AuditIntegrityCheck.objects.exists()


# --- Admin console and commands --------------------------------------------------------------


@pytest.mark.django_db
def test_admin_console_runs_a_check_for_auditors_only(auditor_user, admin_user, sealed):
    console = Client()
    console.force_login(admin_user)
    assert console.get("/admin/audit/auditintegritycheck/").status_code == 403
    assert console.post("/admin/audit/auditintegritycheck/run-check/").status_code == 403

    console.force_login(auditor_user)
    page = console.get("/admin/audit/auditintegritycheck/")
    assert b"Run integrity check now" in page.content
    response = console.post("/admin/audit/auditintegritycheck/run-check/", follow=True)
    check = AuditIntegrityCheck.objects.get()
    assert check.trigger == "on_demand"
    assert b"nothing was changed" in response.content
    assert console.get("/admin/audit/auditchainentry/").status_code == 200


@pytest.mark.django_db
def test_commands_seal_and_check(sealed, capsys):
    _events(1)
    call_command("seal_audit_log")
    assert "Sealed 1 event(s)." in capsys.readouterr().out
    call_command("check_audit_log")
    assert "PASSED" in capsys.readouterr().out
    _without_triggers(("UPDATE audit_events SET reason = 'x' WHERE id = %s", [sealed[0].pk]))
    with pytest.raises(CommandError, match="FAILED"):
        call_command("check_audit_log")


@pytest.mark.parametrize(
    ("chain_keys", "message"),
    [
        (None, "HIMS_AUDIT_CHAIN_KEYS must be set"),
        ("k1:too-short", "must look like 'key-id:secret'"),
    ],
)
def test_production_refuses_to_start_without_chain_keys(chain_keys, message):
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "HIMS_ENV_FILE": "__none__",
        "HIMS_ENVIRONMENT": "production",
        "HIMS_DATABASE_ENVIRONMENT": "production",
        "HIMS_DEPLOYMENT_ID": "guard-test",
        "DJANGO_SECRET_KEY": "x" * 50,
        "DATABASE_URL": "postgres://u:p@db.invalid:5432/h",
        "HIMS_FIELD_ENCRYPTION_KEYS": "k",
    }
    env.pop("HIMS_MFA_REQUIRED_FOR_PRIVILEGED", None)
    env.pop("HIMS_AUDIT_CHAIN_KEYS", None)
    if chain_keys:
        env["HIMS_AUDIT_CHAIN_KEYS"] = chain_keys
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
