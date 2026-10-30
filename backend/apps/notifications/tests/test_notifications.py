"""Notification service (HIMS-NOTIF-001, spec 4.23). Synthetic data only."""

from datetime import timedelta

import pytest
from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend
from django.test import Client, override_settings
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.notifications.backends import LocmemSmsBackend
from apps.notifications.models import Notification
from apps.notifications.services import retry_due, send_email, send_sms

URL = "/api/v1/notifications/"
LINK = "http://app.test/activate#token=SECRET-TOKEN-123"
BROKEN = "apps.notifications.tests.test_notifications.BrokenBackend"


class BrokenBackend(BaseEmailBackend):
    """Simulates the email provider being down."""

    def send_messages(self, email_messages):
        raise ConnectionRefusedError("smtp.example.test refused the connection")


def _send(**extra):
    return send_email(
        to=["nurse@synthetic.test"],
        subject="Activate your account",
        body=f"Open this link:\n{LINK}\n",
        category="account",
        template="identity.invitation",
        **extra,
    )


@pytest.fixture(autouse=True)
def _clear_sms():
    LocmemSmsBackend.outbox.clear()


@pytest.mark.django_db
def test_email_is_sent_and_logged_without_the_secret_link():
    notification = _send()
    assert notification.status == Notification.Status.SENT
    assert notification.attempts == 1
    assert mail.outbox[0].to == ["nurse@synthetic.test"]
    assert LINK in mail.outbox[0].body  # the person gets the real link
    assert "SECRET-TOKEN-123" not in notification.body  # the log does not
    assert "#token=[hidden]" in notification.body
    assert notification.body_encrypted == ""  # delivered: secret copy erased


@pytest.mark.django_db
def test_existing_emails_now_go_through_the_log(admin_user, client_for, make_user):
    from apps.identity.invitations import issue_invitation, send_invitation_email

    person = make_user(email="invitee@synthetic.test", password=None)
    # The email itself is sent by the outbox consumer; call that step directly here.
    send_invitation_email(issue_invitation(user=person, actor=admin_user))
    logged = Notification.objects.get(template="identity.invitation")
    assert logged.recipients == ["invitee@synthetic.test"]
    assert logged.status == Notification.Status.SENT
    assert "#token=[hidden]" in logged.body
    assert "#token=" in mail.outbox[-1].body and "[hidden]" not in mail.outbox[-1].body


@pytest.mark.django_db
def test_a_provider_failure_does_not_break_the_action_and_is_retried():
    with override_settings(EMAIL_BACKEND=BROKEN):
        notification = _send()
    assert notification.status == Notification.Status.FAILED
    assert "ConnectionRefusedError" in notification.last_error
    assert notification.next_attempt_at > timezone.now()
    assert notification.body_encrypted  # kept so it can be sent again

    assert retry_due() == 0  # pause not over yet
    assert retry_due(now=timezone.now() + timedelta(minutes=6)) == 1
    notification.refresh_from_db()
    assert notification.status == Notification.Status.SENT
    assert notification.attempts == 2
    assert LINK in mail.outbox[-1].body


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=BROKEN, HIMS_NOTIFICATION_MAX_ATTEMPTS=2)
def test_gives_up_after_the_last_attempt():
    notification = _send()
    retry_due(now=timezone.now() + timedelta(hours=1))
    notification.refresh_from_db()
    assert notification.status == Notification.Status.GAVE_UP
    assert notification.next_attempt_at is None


@pytest.mark.django_db
def test_sms_is_sent_and_bad_numbers_are_skipped():
    sent = send_sms(
        to=["+919876543210"],
        body="Your appointment is tomorrow 10:20.",
        category="appointment",
        template="test.sms",
    )
    assert sent.status == Notification.Status.SENT
    assert LocmemSmsBackend.outbox == [("+919876543210", "Your appointment is tomorrow 10:20.")]
    skipped = send_sms(to=["98765"], body="x", category="appointment", template="test.sms")
    assert skipped.status == Notification.Status.SKIPPED
    assert "phone number" in skipped.skip_reason


@pytest.mark.django_db
def test_nobody_to_send_to_is_recorded_as_not_sent():
    notification = send_email(to=[], subject="s", body="b", category="x", template="t")
    assert notification.status == Notification.Status.SKIPPED
    assert mail.outbox == []


@pytest.mark.django_db
def test_admin_sees_the_log_sends_again_and_tests(client_for, admin_user):
    with override_settings(EMAIL_BACKEND=BROKEN):
        failed = _send()
    client = client_for(admin_user)
    rows = client.get(URL, {"status": "failed"}).json()["results"]
    assert [r["id"] for r in rows] == [str(failed.pk)]
    assert rows[0]["can_send_again"] is True
    assert "SECRET-TOKEN-123" not in str(rows[0])

    again = client.post(f"{URL}{failed.pk}/send-again/")
    assert again.status_code == 200 and again.json()["status"] == "sent"
    assert client.post(f"{URL}{failed.pk}/send-again/").json()["code"] == "NOT_FAILED"
    assert AuditEvent.objects.filter(action=AuditAction.NOTIFICATION_RETRIED).exists()

    email = client.post(
        URL + "test/", {"channel": "email", "to": "me@synthetic.test"}, format="json"
    )
    assert email.status_code == 201 and email.json()["status"] == "sent"
    sms = client.post(URL + "test/", {"channel": "sms", "to": "+15555550100"}, format="json")
    assert sms.status_code == 201 and LocmemSmsBackend.outbox[-1][0] == "+15555550100"
    bad = client.post(URL + "test/", {"channel": "email", "to": "not-an-email"}, format="json")
    assert bad.status_code == 400
    assert AuditEvent.objects.filter(action=AuditAction.NOTIFICATION_TEST_SENT).count() == 2


@pytest.mark.django_db
def test_people_without_the_permission_cannot_see_messages(client_for, auditor_user):
    client = client_for(auditor_user)
    assert client.get(URL).status_code == 403
    assert (
        client.post(
            URL + "test/", {"channel": "email", "to": "x@synthetic.test"}, format="json"
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_admin_console_lists_and_sends_again(admin_user):
    with override_settings(EMAIL_BACKEND=BROKEN):
        failed = _send()
    console = Client()
    console.force_login(admin_user)
    page = console.get("/admin/notifications/notification/")
    assert page.status_code == 200 and b"identity.invitation" in page.content
    console.post(
        "/admin/notifications/notification/",
        {"action": "send_again", "_selected_action": [str(failed.pk)]},
    )
    failed.refresh_from_db()
    assert failed.status == Notification.Status.SENT
