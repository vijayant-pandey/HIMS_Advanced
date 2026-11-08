"""Outbox clean-up, health and decisions on failed events (HIMS-PLAT-014; spec 14.3).
Synthetic data only."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from common.exceptions import ConflictError
from common.outbox import maintenance
from common.outbox.api import EVENT_LABELS
from common.outbox.maintenance import dismiss, outbox_health, purge_old_events, send_again
from common.outbox.models import OutboxEvent, ProcessedEvent
from common.outbox.registry import _handlers
from config.celery import app as celery_app

API = "/api/v1/background-jobs"
Status = OutboxEvent.Status


def event(status=Status.PUBLISHED, *, days_old=0, minutes_old=0, attempts=0, **extra):
    when = timezone.now() - timedelta(days=days_old, minutes=minutes_old)
    return OutboxEvent.objects.create(
        event_type="staff.member.created",
        customer_id="test-deployment",
        aggregate_type="staff_member",
        aggregate_id="s-1",
        status=status,
        attempts=attempts,
        occurred_at=when,
        published_at=when if status == Status.PUBLISHED else None,
        resolved_at=when if status == Status.DISMISSED else None,
        last_error="ConnectionError" if status == Status.DEAD else "",
        **extra,
    )


def marker(for_event, *, days_old=0):
    row = ProcessedEvent.objects.create(handler="synthetic.handler", event_id=for_event.pk)
    ProcessedEvent.objects.filter(pk=row.pk).update(
        processed_at=timezone.now() - timedelta(days=days_old)
    )
    return row


@pytest.fixture
def admin(make_user, system_roles):
    return make_user(role=system_roles["organization-administrator"])


# --- Clean-up --------------------------------------------------------------------------------


@pytest.mark.django_db
def test_cleanup_deletes_only_old_finished_events_and_markers_that_cannot_be_needed(monkeypatch):
    monkeypatch.setattr(maintenance, "DELETE_BATCH", 2)  # several small batches
    old_done = [event(days_old=40) for _ in range(3)]
    old_dismissed = event(Status.DISMISSED, days_old=40)
    recent_done = event(days_old=5)
    old_waiting = event(Status.PENDING, days_old=40)
    old_failed = event(Status.DEAD, days_old=40)
    for done in old_done:
        marker(done, days_old=40)
    kept_markers = [marker(old_failed, days_old=40), marker(old_waiting, days_old=40)]
    recent_marker = marker(recent_done, days_old=5)

    result = purge_old_events()

    assert result == {"events_deleted": 4, "markers_deleted": 3, "retention_days": 30}
    remaining = set(OutboxEvent.objects.values_list("pk", flat=True))
    assert remaining == {recent_done.pk, old_waiting.pk, old_failed.pk}
    assert old_dismissed.pk not in remaining
    assert set(ProcessedEvent.objects.values_list("pk", flat=True)) == {
        *(m.pk for m in kept_markers),
        recent_marker.pk,
    }
    cleaned = AuditEvent.objects.get(action=AuditAction.OUTBOX_CLEANED_UP)
    assert cleaned.metadata["events_deleted"] == 4


# --- Health ----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_health_counts_waiting_retried_stuck_and_failed():
    event(Status.PENDING, minutes_old=2)
    event(Status.PENDING, minutes_old=45, attempts=3)
    event(Status.DEAD, days_old=1, attempts=12)
    event(days_old=0)
    health = outbox_health()
    assert health["waiting"] == 2 and health["retrying"] == 1 and health["stuck"] == 1
    assert health["failed"] == 1 and health["published_last_24h"] == 1
    assert 44 <= health["oldest_waiting_minutes"] <= 46
    assert health["last_cleanup"] is None
    assert [p.split(" ")[0] for p in health["attention"]] == ["1", "1"]
    purge_old_events()
    assert outbox_health()["last_cleanup"]["events_deleted"] == 0


@pytest.mark.django_db
def test_nothing_needs_a_look_when_all_is_flowing(caplog):
    event(Status.PENDING, minutes_old=1)
    assert maintenance.warn_if_attention_needed() == []
    event(Status.DEAD)
    assert maintenance.warn_if_attention_needed()
    assert "outbox_attention_needed" in caplog.text


# --- Decisions on failed events ----------------------------------------------------------------


@pytest.mark.django_db
def test_send_again_gives_a_failed_event_fresh_retries_and_is_audited(admin):
    failed = event(Status.DEAD, attempts=12)
    sent = send_again(actor=admin, event_id=failed.pk, reason="Email server fixed")
    assert (sent.status, sent.attempts, sent.resolution_note) == (
        Status.PENDING,
        0,
        "Email server fixed",
    )
    audit = AuditEvent.objects.get(action=AuditAction.OUTBOX_EVENT_SENT_AGAIN)
    assert audit.reason == "Email server fixed" and audit.actor_id == admin.pk
    assert audit.changes == {"status": {"before": "dead", "after": "pending"}}


@pytest.mark.django_db
def test_dismiss_closes_a_failed_event_for_good(admin):
    failed = event(Status.DEAD)
    closed = dismiss(actor=admin, event_id=failed.pk, reason="The staff record was a test")
    assert closed.status == Status.DISMISSED and closed.resolved_by_id == admin.pk
    with pytest.raises(ConflictError):
        send_again(actor=admin, event_id=failed.pk, reason="try")  # dismissed is final


@pytest.mark.django_db
def test_decisions_need_a_reason_and_a_failed_event(admin):
    with pytest.raises(ConflictError, match="reason"):
        dismiss(actor=admin, event_id=event(Status.DEAD).pk, reason="  ")
    with pytest.raises(ConflictError):
        dismiss(actor=admin, event_id=event(Status.PENDING).pk, reason="no")
    with pytest.raises(ConflictError):
        send_again(actor=admin, event_id=event().pk, reason="already done")


# --- Screen, permissions, commands, schedule --------------------------------------------------


@pytest.mark.django_db
def test_screen_lists_what_needs_a_look_and_records_decisions(client_for, admin):
    failed = event(Status.DEAD, attempts=12)
    stuck = event(Status.PENDING, minutes_old=60)
    event(Status.PENDING, minutes_old=1)
    client = client_for(admin)
    listed = client.get(f"{API}/").json()
    assert {row["id"] for row in listed} == {str(failed.pk), str(stuck.pk)}
    assert listed[0]["event_label"] == EVENT_LABELS["staff.member.created"]
    assert client.get(f"{API}/health/").json()["failed"] == 1
    refused = client.post(f"{API}/{failed.pk}/dismiss/", {"reason": ""}, format="json")
    assert refused.status_code == 400
    sent = client.post(f"{API}/{failed.pk}/send-again/", {"reason": "Fixed"}, format="json")
    assert sent.status_code == 200 and sent.json()["status"] == "pending"
    assert sent.json()["resolved_by_name"] == admin.display_name
    assert (
        client.post(f"{API}/{stuck.pk}/dismiss/", {"reason": "x"}, format="json").status_code == 409
    )


@pytest.mark.django_db
def test_only_people_with_the_permission_see_or_decide(client_for, make_user, system_roles):
    for role in ("auditor", "basic-staff"):
        client = client_for(make_user(role=system_roles[role]))
        assert client.get(f"{API}/health/").status_code == 403
        failed = event(Status.DEAD)
        body = {"reason": "x"}
        assert client.post(f"{API}/{failed.pk}/dismiss/", body, format="json").status_code == 403


@pytest.mark.django_db
def test_status_command_fails_when_something_needs_a_look():
    out = StringIO()
    call_command("outbox_status", stdout=out)
    assert "OK: nothing needs a look." in out.getvalue()
    event(Status.DEAD)
    with pytest.raises(CommandError, match="outbox-and-background-jobs"):
        call_command("outbox_status", stdout=StringIO(), stderr=StringIO())


@pytest.mark.django_db
def test_cleanup_command_reports_what_it_deleted():
    event(days_old=40)
    out = StringIO()
    call_command("outbox_cleanup", stdout=out)
    assert "Deleted 1 event(s)" in out.getvalue()


def test_cleanup_and_health_check_are_scheduled():
    celery_app.loader.import_default_modules()
    celery_app.finalize()
    tasks = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    assert {"platform.outbox_cleanup", "platform.outbox_health_check"} <= tasks


def test_every_event_with_a_handler_has_words_on_the_screen():
    real = {name for name in _handlers if not name.startswith("test.")}  # tests add their own
    assert real <= set(EVENT_LABELS)
