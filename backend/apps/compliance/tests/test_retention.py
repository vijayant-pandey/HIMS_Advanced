"""Retention purge with legal hold (HIMS-COMP-006). Synthetic data only."""

from datetime import date, timedelta

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.db import DatabaseError, transaction
from django.test import Client
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.compliance import retention
from apps.compliance.models import (
    BrowserSecurityReport,
    ConsoleAccessBlock,
    LegalHold,
    RetentionPurgeRun,
    RetentionRule,
)
from apps.identity import confirmation
from apps.identity.models import Invitation, PasswordReset, UserSession
from apps.notifications.models import Notification
from common.exceptions import ConflictError

STATUS = "/api/v1/retention/"
RUN = "/api/v1/retention/run/"
RUNS = "/api/v1/retention-runs/"
HOLDS = "/api/v1/legal-holds/"
LONG_AGO = timezone.now() - timedelta(days=800)


def period(key):
    return f"/api/v1/retention/periods/{key}/"


@pytest.fixture(autouse=True)
def _clear_throttles():
    cache.clear()


@pytest.fixture
def officer(make_user, system_roles):
    return make_user(role=system_roles["compliance-officer"])


def _in_force(key, days):
    """A period already in force (skips the waiting time, which has its own tests)."""
    retention.sync_rules()
    RetentionRule.objects.filter(category=key).update(keep_days=days)


def _session(user, *, ended_at=None, created_days_ago=800):
    row = UserSession.objects.create(
        user=user, session_key=f"k{UserSession.objects.count()}x{user.pk.hex[:20]}"
    )
    UserSession.objects.filter(pk=row.pk).update(
        created_at=timezone.now() - timedelta(days=created_days_ago), ended_at=ended_at
    )
    return row


def _message(to, *, status=Notification.Status.SENT, created_at=LONG_AGO):
    return Notification.objects.create(
        channel=Notification.Channel.EMAIL,
        category="account",
        template="test",
        recipients=[to],
        subject="Synthetic",
        body="Synthetic message",
        status=status,
        created_at=created_at,
    )


def _deleted(run, key):
    return run.details[key]["deleted"]


# --- Nothing goes until a period is set -------------------------------------------------------


@pytest.mark.django_db
def test_without_periods_nothing_is_deleted_and_the_run_is_recorded(make_user):
    user = make_user()
    _session(user, ended_at=LONG_AGO)
    _message(user.email)
    run = retention.run_purge(trigger=RetentionPurgeRun.Trigger.COMMAND)
    assert run.deleted_total == 0
    assert UserSession.objects.count() == 1 and Notification.objects.count() == 1
    assert {plan["skipped"] for plan in run.details.values()} == {"No period set: kept for ever."}
    event = AuditEvent.objects.get(action=AuditAction.RETENTION_PURGE_RUN)
    assert event.resource_id == str(run.pk)
    assert event.metadata["deleted_total"] == 0


# --- Setting a period -------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_period_below_the_minimum_or_absurdly_long_is_refused(officer):
    retention.sync_rules()
    rule = RetentionRule.objects.get(category="sign_ins")
    for days in (30, retention.MAX_DAYS + 1):
        with pytest.raises(ConflictError, match="keep at least 365 days"):
            retention.set_period(
                actor=officer, category="sign_ins", keep_days=days, version=rule.version
            )


@pytest.mark.django_db
def test_a_first_or_shorter_period_waits_and_a_longer_one_applies_at_once(officer):
    retention.sync_rules()
    rule = RetentionRule.objects.get(category="messages")
    rule = retention.set_period(
        actor=officer, category="messages", keep_days=400, version=rule.version
    )
    assert rule.keep_days is None and rule.pending_keep_days == 400
    assert rule.pending_from > timezone.now() + timedelta(days=6)
    assert retention.apply_due_periods() == []  # not yet

    applied = retention.apply_due_periods(now=rule.pending_from)
    assert applied == ["messages"]
    rule.refresh_from_db()
    assert (rule.keep_days, rule.pending_keep_days, rule.pending_from) == (400, None, None)
    assert AuditEvent.objects.filter(action=AuditAction.RETENTION_PERIOD_APPLIED).count() == 1

    rule = retention.set_period(
        actor=officer, category="messages", keep_days=200, version=rule.version
    )
    assert (rule.keep_days, rule.pending_keep_days) == (400, 200)  # shorter: waits
    rule = retention.set_period(
        actor=officer, category="messages", keep_days=400, version=rule.version
    )
    assert (rule.keep_days, rule.pending_keep_days) == (400, None)  # same as now: cancelled
    rule = retention.set_period(
        actor=officer, category="messages", keep_days=500, version=rule.version
    )
    assert rule.keep_days == 500  # longer: at once
    rule = retention.set_period(
        actor=officer, category="messages", keep_days=None, version=rule.version
    )
    assert rule.keep_days is None  # for ever: at once
    with pytest.raises(ConflictError, match="already set"):
        retention.set_period(
            actor=officer, category="messages", keep_days=None, version=rule.version
        )
    changes = AuditEvent.objects.filter(action=AuditAction.RETENTION_PERIOD_CHANGED)
    assert changes.count() == 5


# --- What each kind deletes -------------------------------------------------------------------


@pytest.mark.django_db
def test_only_closed_rows_past_the_period_are_deleted(make_user, admin_user):
    user = make_user()
    for key, days in (
        ("sign_ins", 365),
        ("messages", 90),
        ("invitations", 30),
        ("password_resets", 30),
        ("browser_reports", 30),
        ("console_refusals", 365),
    ):
        _in_force(key, days)
    now = timezone.now()
    old_ended = _session(user, ended_at=LONG_AGO)
    old_open = _session(user)
    recent_ended = _session(user, ended_at=now - timedelta(days=10), created_days_ago=11)
    sent = _message(user.email)
    waiting = _message(user.email, status=Notification.Status.PENDING)
    recent = _message(user.email, created_at=now - timedelta(days=5))
    accepted = Invitation.objects.create(user=user, expires_at=LONG_AGO, accepted_at=LONG_AGO)
    Invitation.objects.filter(pk=accepted.pk).update(created_at=LONG_AGO)
    other = make_user()
    open_invite = Invitation.objects.create(user=other, expires_at=now + timedelta(days=1))
    Invitation.objects.filter(pk=open_invite.pk).update(created_at=LONG_AGO)
    reset = PasswordReset.objects.create(user=user, expires_at=LONG_AGO)
    PasswordReset.objects.filter(pk=reset.pk).update(created_at=LONG_AGO)
    BrowserSecurityReport.objects.create(
        day=date(2024, 1, 2), directive="script-src", blocked="https://evil.example"
    )
    BrowserSecurityReport.objects.create(
        day=now.date(), directive="script-src", blocked="https://evil.example"
    )
    ConsoleAccessBlock.objects.create(
        day=date(2024, 1, 2), ip_address="203.0.113.9", reviewed_at=now, reviewed_by=admin_user
    )
    unreviewed = ConsoleAccessBlock.objects.create(day=date(2024, 1, 3), ip_address="203.0.113.10")

    run = retention.run_purge(trigger=RetentionPurgeRun.Trigger.COMMAND)

    assert {key: _deleted(run, key) for key in retention.CATEGORIES} == {
        "sign_ins": 1,
        "messages": 1,
        "invitations": 1,
        "password_resets": 1,
        "browser_reports": 1,
        "console_refusals": 1,
    }
    assert run.deleted_total == 6
    assert set(UserSession.objects.values_list("pk", flat=True)) == {old_open.pk, recent_ended.pk}
    assert not UserSession.objects.filter(pk=old_ended.pk).exists()
    assert set(Notification.objects.values_list("pk", flat=True)) == {waiting.pk, recent.pk}
    assert not Notification.objects.filter(pk=sent.pk).exists()
    assert list(Invitation.objects.values_list("pk", flat=True)) == [open_invite.pk]
    assert not PasswordReset.objects.exists()
    assert BrowserSecurityReport.objects.get().day == now.date()
    assert list(ConsoleAccessBlock.objects.values_list("pk", flat=True)) == [unreviewed.pk]


# --- Legal holds ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_hold_on_a_whole_kind_stops_its_purge_until_released(officer, make_user):
    user = make_user()
    _in_force("sign_ins", 365)
    _session(user, ended_at=LONG_AGO)
    hold = retention.place_hold(
        actor=officer,
        reference="Matter 2026-14",
        reason="Expected dispute",
        categories=["sign_ins"],
    )
    run = retention.run_purge(trigger=RetentionPurgeRun.Trigger.COMMAND)
    assert run.details["sign_ins"]["skipped"] == "A legal hold covers all of these."
    assert run.details["sign_ins"]["held"] == 1
    assert UserSession.objects.count() == 1

    with pytest.raises(ConflictError, match="Say why"):
        retention.release_hold(actor=officer, hold_id=hold.pk, version=hold.version, reason=" ")
    hold = retention.release_hold(
        actor=officer, hold_id=hold.pk, version=hold.version, reason="Matter settled"
    )
    with pytest.raises(ConflictError, match="already released"):
        retention.release_hold(actor=officer, hold_id=hold.pk, version=hold.version, reason="Again")
    run = retention.run_purge(trigger=RetentionPurgeRun.Trigger.COMMAND)
    assert _deleted(run, "sign_ins") == 1
    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {AuditAction.LEGAL_HOLD_PLACED, AuditAction.LEGAL_HOLD_RELEASED} <= actions


@pytest.mark.django_db
def test_a_hold_on_one_person_keeps_only_their_records(officer, make_user):
    held, other = make_user(), make_user()
    for key in ("sign_ins", "messages"):
        _in_force(key, 365)
    _session(held, ended_at=LONG_AGO)
    _session(other, ended_at=LONG_AGO)
    _message(held.email)
    _message(other.email)
    retention.place_hold(
        actor=officer, reference="HR-7", reason="Employment claim", subject_user=held
    )
    plan = retention.preview()["sign_ins"]
    assert (plan["keep_days"], plan["skipped"], plan["held"], plan["would_delete"]) == (
        365,
        "",
        1,
        1,
    )
    run = retention.run_purge(trigger=RetentionPurgeRun.Trigger.COMMAND)
    assert (_deleted(run, "sign_ins"), run.details["sign_ins"]["held"]) == (1, 1)
    assert (_deleted(run, "messages"), run.details["messages"]["held"]) == (1, 1)
    assert list(UserSession.objects.values_list("user_id", flat=True)) == [held.pk]
    assert Notification.objects.get().recipients == [held.email]


@pytest.mark.django_db
def test_unknown_kinds_and_empty_reasons_are_refused(officer):
    with pytest.raises(ConflictError, match="No such kind"):
        retention.place_hold(actor=officer, reference="X", reason="Y", categories=["patients"])
    with pytest.raises(ConflictError, match="reference and the reason"):
        retention.place_hold(actor=officer, reference="X", reason=" ")


# --- Evidence ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_purge_runs_cannot_be_changed_or_deleted():
    run = retention.run_purge(trigger=RetentionPurgeRun.Trigger.COMMAND)
    with pytest.raises(DatabaseError), transaction.atomic():
        RetentionPurgeRun.objects.filter(pk=run.pk).update(deleted_total=99)
    with pytest.raises(DatabaseError), transaction.atomic():
        RetentionPurgeRun.objects.filter(pk=run.pk).delete()


# --- API --------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_retention_tab_shows_each_kind_with_its_preview(client_for, officer, make_user):
    _in_force("sign_ins", 365)
    _session(make_user(), ended_at=LONG_AGO)
    body = client_for(officer).get(STATUS).json()
    assert [row["category"] for row in body["categories"]] == list(retention.CATEGORIES)
    sign_ins = body["categories"][0]
    assert (sign_ins["keep_days"], sign_ins["minimum_days"], sign_ins["would_delete"]) == (
        365,
        365,
        1,
    )
    assert body["categories"][1]["skipped"] == "No period set: kept for ever."
    assert (body["wait_days"], body["active_holds"], body["last_run"]) == (7, 0, None)


@pytest.mark.django_db
def test_officer_sets_periods_places_holds_and_runs_the_purge(client_for, officer, make_user):
    client = client_for(officer)
    version = client.get(STATUS).json()["categories"][1]["version"]
    response = client.post(period("messages"), {"keep_days": 120, "version": version}, "json")
    assert response.status_code == 200
    messages = response.json()["categories"][1]
    assert (messages["keep_days"], messages["pending_keep_days"]) == (None, 120)
    assert (
        client.post(period("messages"), {"keep_days": 5, "version": 2}, "json").status_code == 409
    )
    assert (
        client.post(period("patients"), {"keep_days": 500, "version": 1}, "json").status_code == 404
    )

    held = make_user()
    response = client.post(
        HOLDS,
        {
            "reference": "Matter 2026-15",
            "reason": "Investigation",
            "categories": ["messages"],
            "subject_email": held.email.upper(),
        },
        "json",
    )
    assert response.status_code == 201
    hold = response.json()
    assert (hold["subject_email"], hold["categories"], hold["is_active"]) == (
        held.email,
        ["messages"],
        True,
    )
    bad = client.post(
        HOLDS, {"reference": "M", "reason": "R", "subject_email": "nobody@synthetic.test"}, "json"
    )
    assert bad.status_code == 400
    assert (
        client.post(
            HOLDS, {"reference": "M", "reason": "R", "categories": ["x"]}, "json"
        ).status_code
        == 400
    )

    run = client.post(RUN)
    assert run.status_code == 201
    assert (run.json()["trigger"], run.json()["run_by_name"]) == ("manual", officer.display_name)
    assert len(client.get(RUNS).json()) == 1

    released = client.post(
        f"{HOLDS}{hold['id']}/release/", {"version": hold["version"], "reason": "Closed"}, "json"
    )
    assert released.status_code == 200 and released.json()["is_active"] is False
    assert client.get(f"{HOLDS}?active=true").json() == []


@pytest.mark.django_db
def test_viewers_cannot_change_anything(client_for, auditor_user):
    client = client_for(auditor_user)
    assert client.get(STATUS).status_code == 200
    assert client.get(HOLDS).status_code == 200
    assert client.post(RUN).status_code == 403
    assert (
        client.post(period("messages"), {"keep_days": 120, "version": 1}, "json").status_code == 403
    )
    assert client.post(HOLDS, {"reference": "M", "reason": "R"}, "json").status_code == 403
    assert client_for().get(STATUS).status_code in (401, 403)


@pytest.mark.django_db
def test_changes_need_a_recent_confirm_its_you(client_for, officer):
    client = client_for(officer)
    session = client.session
    session[confirmation.SESSION_CONFIRMED_KEY] = (timezone.now() - timedelta(hours=1)).timestamp()
    session.save()
    for response in (
        client.post(RUN),
        client.post(period("messages"), {"keep_days": 120, "version": 1}, "json"),
        client.post(HOLDS, {"reference": "M", "reason": "R"}, "json"),
    ):
        assert response.status_code == 403
        assert response.json()["code"] == "REAUTH_REQUIRED"
    assert not RetentionPurgeRun.objects.exists() and not LegalHold.objects.exists()


# --- Admin console, job and command -----------------------------------------------------------


def _console(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_console_sets_a_period_places_a_hold_and_runs_the_purge(admin_user, make_user):
    retention.sync_rules()
    client = _console(admin_user)
    rule = RetentionRule.objects.get(category="browser_reports")
    url = f"/admin/compliance/retentionrule/{rule.pk}/change/"
    assert client.post(url, {"keep_days": 5}).status_code == 200  # below the minimum: shown again
    assert client.post(url, {"keep_days": 60}).status_code == 302
    rule.refresh_from_db()
    assert (rule.keep_days, rule.pending_keep_days) == (None, 60)
    assert client.post(url, {"keep_days": "", "cancel_pending": "on"}).status_code == 302
    rule.refresh_from_db()
    assert rule.pending_keep_days is None

    person = make_user()
    response = client.post(
        "/admin/compliance/legalhold/add/",
        {
            "reference": "Matter 9",
            "reason": "Synthetic dispute",
            "hold_categories": ["sign_ins"],
            "subject_user": str(person.pk),
        },
    )
    assert response.status_code == 302
    hold = LegalHold.objects.get()
    assert (hold.categories, hold.subject_user, hold.placed_by) == (
        ["sign_ins"],
        person,
        admin_user,
    )
    client.post(f"/admin/compliance/legalhold/{hold.pk}/change/", {"release_reason": "Settled"})
    hold.refresh_from_db()
    assert hold.released_by == admin_user and hold.release_reason == "Settled"

    assert client.get("/admin/compliance/retentionpurgerun/").status_code == 200
    response = client.post("/admin/compliance/retentionpurgerun/run-now/")
    run = RetentionPurgeRun.objects.get()
    assert response.status_code == 302 and run.run_by == admin_user
    assert client.get(f"/admin/compliance/retentionpurgerun/{run.pk}/change/").status_code == 200


@pytest.mark.django_db
def test_console_run_now_needs_confirm_its_you(admin_user):
    client = _console(admin_user)
    session = client.session
    session[confirmation.SESSION_CONFIRMED_KEY] = (timezone.now() - timedelta(hours=1)).timestamp()
    session.save()
    response = client.post("/admin/compliance/retentionpurgerun/run-now/")
    assert response.status_code == 302 and "confirm" in response["Location"]
    assert not RetentionPurgeRun.objects.exists()


@pytest.mark.django_db
def test_daily_job_is_scheduled_and_the_command_can_dry_run(capsys, make_user):
    from config.celery import app as celery_app

    celery_app.loader.import_default_modules()
    celery_app.finalize()
    tasks = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    assert "platform.retention_purge" in tasks

    _in_force("sign_ins", 365)
    _session(make_user(), ended_at=LONG_AGO)
    call_command("purge_expired_records", "--dry-run")
    out = capsys.readouterr().out
    assert "Sign-in register: would delete 1, kept by legal hold 0" in out
    assert UserSession.objects.count() == 1 and not RetentionPurgeRun.objects.exists()
    call_command("purge_expired_records")
    assert "Deleted 1 record(s)." in capsys.readouterr().out
    assert RetentionPurgeRun.objects.get().trigger == "command"
