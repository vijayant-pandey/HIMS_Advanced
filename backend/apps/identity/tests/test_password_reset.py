"""Forgotten-password recovery (HIMS-IAM-004)."""

import re
from datetime import timedelta

import pytest
from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.identity.models import PasswordReset, User
from apps.identity.password_reset import make_token
from common.outbox.dispatcher import dispatch_pending, process_event

OLD_PASSWORD = "Synthetic-Old-Passw0rd-2026"
NEW_PASSWORD = "Synthetic-New-Passw0rd-2026"
SAME_ANSWER = (
    "If an active account uses this email, we have sent a link to reset the password. "
    "Check your inbox."
)


def drain_outbox() -> None:
    while dispatch_pending(publish=lambda event: process_event(event.pk)):
        pass


def public_client() -> tuple[APIClient, str]:
    client = APIClient(enforce_csrf_checks=True)
    client.get("/api/v1/auth/csrf/")
    return client, client.cookies["hims_csrftoken"].value


def request_reset(email: str):
    client, csrf = public_client()
    response = client.post(
        "/api/v1/auth/password-reset/request/",
        {"email": email},
        format="json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    drain_outbox()
    return response


def confirm(token: str, password: str = NEW_PASSWORD):
    client, csrf = public_client()
    return client.post(
        "/api/v1/auth/password-reset/confirm/",
        {"token": token, "password": password},
        format="json",
        HTTP_X_CSRFTOKEN=csrf,
    )


def token_from_last_email() -> str:
    match = re.search(r"/reset-password#token=(\S+)", mail.outbox[-1].body)
    assert match, mail.outbox[-1].body
    return match.group(1)


@pytest.fixture
def account(organization):
    return User.objects.create_user(
        email="nurse@synthetic.test", display_name="Nurse Joy", password=OLD_PASSWORD
    )


@pytest.mark.django_db
def test_reset_email_is_sent_for_an_active_account(account):
    response = request_reset("Nurse@Synthetic.test")
    assert response.status_code == 202
    assert response.json()["detail"] == SAME_ANSWER
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["nurse@synthetic.test"]
    assert "http://app.test/reset-password#token=" in mail.outbox[0].body


@pytest.mark.django_db
def test_unknown_inactive_and_unactivated_accounts_get_the_same_answer(organization):
    User.objects.create_user(
        email="gone@synthetic.test", display_name="Gone", password=OLD_PASSWORD, is_active=False
    )
    User.objects.create_user(
        email="invited@synthetic.test", display_name="Invited"
    )  # no password yet

    for email in ["nobody@synthetic.test", "gone@synthetic.test", "invited@synthetic.test"]:
        response = request_reset(email)
        assert response.status_code == 202
        assert response.json()["detail"] == SAME_ANSWER
    assert mail.outbox == []
    assert not PasswordReset.objects.exists()
    # Attempts are still visible to auditors, without storing the unknown address itself.
    failures = AuditEvent.objects.filter(
        action=AuditAction.PASSWORD_RESET_REQUESTED, outcome=AuditEvent.Outcome.FAILURE
    )
    assert failures.count() == 3
    assert all("email_fingerprint" in event.metadata for event in failures)
    assert not failures.filter(metadata__icontains="nobody@synthetic.test").exists()


@pytest.mark.django_db
@override_settings(HIMS_PASSWORD_RESET_MAX_PER_HOUR=2)
def test_reset_emails_are_capped_per_hour(account):
    for _ in range(4):
        assert request_reset(account.email).status_code == 202
    assert len(mail.outbox) == 2


@pytest.mark.django_db
def test_new_password_works_and_signs_out_every_other_session(account):
    signed_in = APIClient()
    signed_in.force_login(account)
    assert signed_in.get("/api/v1/auth/me/").status_code == 200

    request_reset(account.email)
    token = token_from_last_email()
    assert confirm(token).status_code == 204

    account.refresh_from_db()
    assert account.check_password(NEW_PASSWORD)
    assert signed_in.get("/api/v1/auth/me/").status_code == 401  # old session is gone
    assert AuditEvent.objects.filter(
        action=AuditAction.PASSWORD_RESET_COMPLETED, actor_id=account.pk
    ).exists()

    drain_outbox()
    assert "password was changed" in mail.outbox[-1].subject


@pytest.mark.django_db
def test_link_is_single_use_and_older_links_stop_working(account):
    request_reset(account.email)
    first = token_from_last_email()
    request_reset(account.email)
    second = token_from_last_email()

    assert confirm(first).status_code == 400  # replaced by the newer request
    assert confirm(second).status_code == 204
    reused = confirm(second, password="Yet-Another-Passw0rd-26")
    assert reused.status_code == 400
    assert reused.json()["code"] == "PASSWORD_RESET_INVALID"
    assert AuditEvent.objects.filter(action=AuditAction.PASSWORD_RESET_REJECTED).count() == 2


@pytest.mark.django_db
def test_expired_link_is_rejected(account):
    reset = PasswordReset.objects.create(
        user=account, expires_at=timezone.now() - timedelta(minutes=1)
    )
    assert confirm(make_token(reset)).status_code == 400


@pytest.mark.django_db
def test_weak_password_keeps_link_usable(account):
    request_reset(account.email)
    token = token_from_last_email()
    weak = confirm(token, password="password")
    assert weak.status_code == 400
    assert {error["field"] for error in weak.json()["errors"]} == {"password"}
    assert confirm(token).status_code == 204


@pytest.mark.django_db
def test_invitation_token_cannot_be_used_as_reset_token(account):
    from apps.identity.invitations import make_token as make_invitation_token
    from apps.identity.models import Invitation

    invitation = Invitation.objects.create(
        user=account, expires_at=timezone.now() + timedelta(hours=1)
    )
    assert confirm(make_invitation_token(invitation)).status_code == 400


@pytest.mark.django_db
def test_reset_endpoints_require_csrf(account):
    client = APIClient(enforce_csrf_checks=True)
    response = client.post(
        "/api/v1/auth/password-reset/request/", {"email": account.email}, format="json"
    )
    assert response.status_code == 403
