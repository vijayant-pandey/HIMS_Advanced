"""What the app could do but the admin console could not, added with HIMS-SEC-015 (ADR-016).

Each uses the same service as the app, so the rules and the audit are the same: dismissing a
failed background event (with a typed reason) and its health summary, sending a test message,
and downloading an access review or audit events as CSV (after "confirm it's you").
"""

from datetime import timedelta

import pytest
from django.core import mail
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from apps.access_control.reviews import start_review
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.identity import confirmation
from apps.notifications.models import Notification
from common.outbox.models import OutboxEvent
from common.tests.test_outbox_maintenance import event

Status = OutboxEvent.Status
JOBS = "/admin/outbox/outboxevent/"


@pytest.fixture(autouse=True)
def _clear_lockouts():
    cache.clear()


def console(user, *, confirmed=False):
    """Signing in counts as confirming, so "not confirmed" means it was over an hour ago."""
    client = Client()
    client.force_login(user)
    when = timezone.now() - (timedelta() if confirmed else timedelta(hours=1))
    session = client.session
    session[confirmation.SESSION_CONFIRMED_KEY] = when.timestamp()
    session.save()
    return client


@pytest.mark.django_db
def test_background_jobs_page_shows_the_health_summary(admin_user):
    event(Status.DEAD, attempts=8)
    page = console(admin_user).get(JOBS).content.decode()
    assert "Health" in page
    assert "failed after every retry and need a decision" in page


@pytest.mark.django_db
def test_dismissing_asks_for_a_reason_and_is_audited(admin_user):
    failed, waiting = event(Status.DEAD, attempts=8), event(Status.PENDING)
    client = console(admin_user)
    chosen = {"action": "dismiss_selected", "_selected_action": [str(failed.pk), str(waiting.pk)]}
    asked = client.post(JOBS, chosen)
    assert asked.status_code == 200
    assert "Say why" in asked.content.decode()
    assert "1 selected event(s) have not failed" in asked.content.decode()
    # No reason: nothing is dismissed.
    client.post(JOBS, {**chosen, "apply": "1", "reason": "  "})
    failed.refresh_from_db()
    assert failed.status == Status.DEAD
    client.post(JOBS, {**chosen, "apply": "1", "reason": "The staff record was merged"})
    failed.refresh_from_db()
    waiting.refresh_from_db()
    assert (failed.status, failed.resolution_note) == (
        Status.DISMISSED,
        "The staff record was merged",
    )
    assert waiting.status == Status.PENDING
    audited = AuditEvent.objects.get(action=AuditAction.OUTBOX_EVENT_DISMISSED)
    assert audited.reason == "The staff record was merged"
    assert audited.actor_id == admin_user.pk


@pytest.mark.django_db
def test_sending_a_test_message_from_the_console(admin_user):
    client = console(admin_user)
    url = "/admin/notifications/notification/send-test/"
    assert b"Send a test message" in client.get("/admin/notifications/notification/").content
    assert client.get(url).status_code == 200
    wrong = client.post(url, {"channel": "email", "to": "not-an-email"})
    assert b"Enter a valid email address." in wrong.content
    response = client.post(url, {"channel": "email", "to": "it.desk@synthetic.test"})
    assert response.status_code == 302
    assert mail.outbox[-1].to == ["it.desk@synthetic.test"]
    assert Notification.objects.get().template == "notifications.test"
    assert AuditEvent.objects.filter(action=AuditAction.NOTIFICATION_TEST_SENT).exists()


@pytest.mark.django_db
def test_test_message_needs_notifications_manage(auditor_user):
    url = "/admin/notifications/notification/send-test/"
    assert console(auditor_user).get(url).status_code == 403


@pytest.mark.django_db
def test_access_review_downloads_as_csv_after_confirming(admin_user, organization):
    review = start_review(actor=admin_user, organization=organization, title="Quarterly review")
    page = f"/admin/access_control/accessreview/{review.pk}/change/"
    export = f"/admin/access_control/accessreview/{review.pk}/export/"
    assert b"Download as CSV" in console(admin_user).get(page).content
    asked = console(admin_user).post(export)
    assert asked.status_code == 302
    assert "/admin/confirm-identity/" in asked["Location"]
    assert not AuditEvent.objects.filter(action=AuditAction.ACCESS_REVIEW_EXPORTED).exists()
    response = console(admin_user, confirmed=True).post(export)
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert response.content.decode().startswith("Review,Review status,Person,Email")
    assert AuditEvent.objects.filter(
        action=AuditAction.ACCESS_REVIEW_EXPORTED, resource_id=str(review.pk)
    ).exists()


@pytest.mark.django_db
def test_auditor_downloads_audit_events_as_csv_after_confirming(auditor_user, admin_user):
    chosen = AuditEvent.objects.filter(actor_id=admin_user.pk).first() or AuditEvent.objects.first()
    body = {"action": "download_csv", "_selected_action": [str(chosen.pk)]}
    url = "/admin/audit/auditevent/"
    asked = console(auditor_user).post(url, body)
    assert asked.status_code == 302
    assert "/admin/confirm-identity/" in asked["Location"]
    response = console(auditor_user, confirmed=True).post(url, body)
    lines = b"".join(response.streaming_content).decode().splitlines()
    assert lines[0].startswith("When (UTC),What happened,Action code")
    assert len(lines) == 2
    exported = AuditEvent.objects.get(action=AuditAction.AUDIT_EXPORTED)
    assert exported.metadata["via"] == "admin-console"
    assert exported.metadata["rows"] == 1
    # Administrators cannot see the audit log, so they cannot download it either.
    assert console(admin_user, confirmed=True).post(url, body).status_code == 403
