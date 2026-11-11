"""Scheduled jobs without an always-on scheduler (spec 14; HIMS-OPS-023). Synthetic data."""

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import Client
from django.utils import timezone

from common.outbox import scheduler
from common.outbox.models import OutboxEvent, ScheduledJob
from common.outbox.services import publish_event
from config.schedule import LABELS, SCHEDULE, beat_schedule

SHORT = {name for name, job in SCHEDULE.items() if job["every"] <= timedelta(minutes=1)}


def test_beat_and_the_command_read_the_same_list():
    assert set(beat_schedule()) == set(SCHEDULE) == set(LABELS)
    for name, entry in beat_schedule().items():
        assert entry["task"] == SCHEDULE[name]["task"]
        assert entry["schedule"] == SCHEDULE[name]["every"]


@pytest.mark.django_db(transaction=True)
def test_every_job_runs_once_and_only_short_ones_run_again_at_once(organization):
    first = scheduler.run_due()
    assert not first["busy"]
    failed = [item for item in first["ran"] if item["error"]]
    assert failed == [], failed  # every scheduled job works without a worker
    assert {item["job"] for item in first["ran"]} == set(SCHEDULE)
    assert ScheduledJob.objects.count() == len(SCHEDULE)

    later = timezone.now() + timedelta(seconds=70)
    second = scheduler.run_due(now=later)
    assert {item["job"] for item in second["ran"]} == SHORT  # dispatch and audit sealing
    row = ScheduledJob.objects.get(name="audit-seal-events")
    assert (row.runs, row.failures, row.last_outcome) == (2, 0, ScheduledJob.Outcome.OK)


@pytest.mark.django_db(transaction=True)
def test_a_failing_job_does_not_stop_the_others_and_is_tried_again_soon(organization):
    def broken(*args, **kwargs):
        raise RuntimeError("synthetic failure")

    task = scheduler._tasks()["platform.retention_purge"]
    with patch.object(task, "run", side_effect=broken):
        result = scheduler.run_due()
    errors = {item["job"]: item["error"] for item in result["ran"] if item["error"]}
    assert list(errors) == ["retention-purge"]
    assert "synthetic failure" in errors["retention-purge"]
    assert len(result["ran"]) == len(SCHEDULE)  # the others still ran
    row = ScheduledJob.objects.get(name="retention-purge")
    assert (row.last_outcome, row.failures) == (ScheduledJob.Outcome.FAILED, 1)

    # A daily job that failed is due again after a few minutes, not tomorrow.
    soon = timezone.now() + scheduler.RETRY_AFTER + timedelta(seconds=1)
    again = {item["job"] for item in scheduler.run_due(now=soon)["ran"]}
    assert "retention-purge" in again
    assert "audit-integrity-check" not in again  # it worked, so it waits a day


@pytest.mark.django_db(transaction=True)
def test_two_runs_never_overlap(organization):
    from apps.recovery.pg_tools import connect

    with connect(dict(connection.settings_dict)) as other:
        other.execute("SELECT pg_advisory_lock(%s)", [scheduler._LOCK])
        try:
            assert scheduler.run_due() == {"busy": True, "ran": []}
        finally:
            other.execute("SELECT pg_advisory_unlock(%s)", [scheduler._LOCK])
    assert not ScheduledJob.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_without_a_broker_waiting_events_are_handled_here(organization, settings):
    settings.HIMS_OUTBOX_DISPATCH_INLINE = True
    with patch("common.outbox.services.transaction.on_commit"):  # leave it waiting
        from django.db import transaction

        with transaction.atomic():
            event = publish_event(
                event_type="synthetic.waiting",
                aggregate_type="test",
                aggregate_id=str(uuid.uuid4()),
                payload={},
            )
    assert OutboxEvent.objects.get(pk=event.pk).status == OutboxEvent.Status.PENDING
    call_command("run_scheduled_jobs", "--only", "outbox-dispatch")
    assert OutboxEvent.objects.get(pk=event.pk).status == OutboxEvent.Status.PUBLISHED


@pytest.mark.django_db
def test_command_options(capsys):
    call_command("run_scheduled_jobs", "--list")
    assert "audit-seal-events" in capsys.readouterr().out
    assert not ScheduledJob.objects.exists()  # listing runs nothing
    with pytest.raises(CommandError, match="No scheduled job called"):
        call_command("run_scheduled_jobs", "--only", "no-such-job")


@pytest.mark.django_db
def test_schedule_on_the_background_jobs_page_and_console(client_for, admin_user, make_user):
    ScheduledJob.objects.create(
        name="audit-seal-events",
        task="platform.audit_seal_events",
        every_seconds=60,
        last_started_at=timezone.now(),
        last_outcome=ScheduledJob.Outcome.OK,
        runs=3,
    )
    rows = client_for(admin_user).get("/api/v1/background-jobs/schedule/").json()
    assert [row["name"] for row in rows] == list(SCHEDULE)
    seal = next(row for row in rows if row["name"] == "audit-seal-events")
    assert (seal["label"], seal["runs"], seal["last_outcome"]) == ("Seal the audit log", 3, "ok")
    assert client_for(make_user()).get("/api/v1/background-jobs/schedule/").status_code == 403

    console = Client()
    console.force_login(admin_user)
    page = console.get("/admin/outbox/scheduledjob/").content.decode()
    assert "Seal the audit log" in page


# --- An outside timer over HTTPS (HIMS-OPS-024) ------------------------------------------------

RUN = "/api/v1/scheduled-jobs/run/"
TIMER = "synthetic-timer-value-0000"


@pytest.mark.django_db
def test_the_timer_address_is_off_without_its_setting():
    from rest_framework.test import APIClient

    assert APIClient().post(RUN, HTTP_X_HIMS_SCHEDULER_TOKEN=TIMER).status_code == 404


@pytest.mark.django_db(transaction=True)
def test_the_timer_address_needs_the_right_value_and_runs_due_jobs(organization, settings):
    from rest_framework.test import APIClient

    from apps.audit.models import AuditEvent
    from apps.audit.services import AuditAction

    settings.HIMS_SCHEDULER_TOKEN = TIMER
    caller = APIClient()
    assert caller.post(RUN).status_code == 403
    assert caller.post(RUN, HTTP_X_HIMS_SCHEDULER_TOKEN="wrong-value-0000").status_code == 403
    assert AuditEvent.objects.filter(action=AuditAction.ACCESS_DENIED).count() == 2
    assert not ScheduledJob.objects.exists()

    response = caller.post(RUN, HTTP_X_HIMS_SCHEDULER_TOKEN=TIMER)
    assert response.status_code == 200
    assert response.json() == {"busy": False, "ran": len(SCHEDULE), "failed": 0}
    again = caller.post(RUN, HTTP_X_HIMS_SCHEDULER_TOKEN=TIMER).json()
    assert again["ran"] == 1  # at once, only the every-5-seconds job is due again
