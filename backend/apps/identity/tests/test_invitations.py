"""Staff invitation and account activation (HIMS-IAM-003)."""

import re
from datetime import timedelta

import pytest
from django.core import mail
from django.test import Client, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.identity.invitations import issue_invitation, make_token
from apps.identity.models import Invitation, User
from common.outbox.dispatcher import dispatch_pending, process_event
from common.outbox.models import OutboxEvent

NEW_PASSWORD = "Synthetic-New-Passw0rd-2026"
DOCTOR = {
    "email": "new.doctor@synthetic.test",
    "employee_number": "EMP-INV-1",
    "given_name": "Meera",
    "family_name": "Iyer",
    "staff_type": "doctor",
    "joined_on": "2026-02-01",
}


def drain_outbox() -> None:
    """Process events (and the events their handlers publish) like the worker would."""
    while dispatch_pending(publish=lambda event: process_event(event.pk)):
        pass


def token_from_last_email() -> str:
    match = re.search(r"/activate#token=(\S+)", mail.outbox[-1].body)
    assert match, mail.outbox[-1].body
    return match.group(1)


def public_client() -> tuple[APIClient, str]:
    client = APIClient(enforce_csrf_checks=True)
    client.get("/api/v1/auth/csrf/")
    return client, client.cookies["hims_csrftoken"].value


def accept(client, csrf, token, password=NEW_PASSWORD):
    return client.post(
        "/api/v1/auth/invitations/accept/",
        {"token": token, "password": password},
        format="json",
        HTTP_X_CSRFTOKEN=csrf,
    )


@pytest.fixture
def invited_user(organization):
    user = User.objects.create_user(email="invitee@synthetic.test", display_name="Invitee")
    invitation = issue_invitation(user=user)
    return user, invitation


@pytest.mark.django_db
def test_new_staff_member_receives_activation_email(client_for, admin_user):
    response = client_for(admin_user).post("/api/v1/staff/", DOCTOR, format="json")
    assert response.status_code == 201
    drain_outbox()

    assert len(mail.outbox) == 1
    email = mail.outbox[0]
    assert email.to == ["new.doctor@synthetic.test"]
    assert "Synthetic Health" in email.subject
    assert "http://app.test/activate#token=" in email.body  # token only in the URL fragment

    # The secret never sits in the database: not in invitations, not in outbox payloads.
    token = token_from_last_email()
    assert not OutboxEvent.objects.filter(payload__icontains=token).exists()
    assert Invitation.objects.get(user__email="new.doctor@synthetic.test").status == "open"


@pytest.mark.django_db
@override_settings(HIMS_OUTBOX_DISPATCH_INLINE=True)
def test_inline_outbox_mode_sends_email_without_a_worker(
    client_for, admin_user, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = client_for(admin_user).post("/api/v1/staff/", DOCTOR, format="json")
    assert response.status_code == 201
    assert len(mail.outbox) == 1
    assert not OutboxEvent.objects.filter(status=OutboxEvent.Status.PENDING).exists()


@pytest.mark.django_db
def test_activation_sets_password_signs_in_and_is_single_use(invited_user):
    user, invitation = invited_user
    client, csrf = public_client()
    token = make_token(invitation)

    details = client.post(
        "/api/v1/auth/invitations/inspect/", {"token": token}, format="json", HTTP_X_CSRFTOKEN=csrf
    )
    assert details.status_code == 200
    assert details.json()["email"] == "invitee@synthetic.test"
    assert details.json()["organization_name"] == "Synthetic Health"

    response = accept(client, csrf, token)
    assert response.status_code == 200
    assert response.json()["email"] == "invitee@synthetic.test"
    assert client.get("/api/v1/auth/me/").status_code == 200  # signed in

    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    assert user.password_changed_at is not None
    assert AuditEvent.objects.filter(
        action=AuditAction.USER_INVITATION_ACCEPTED, actor_id=user.pk
    ).exists()

    again, csrf = public_client()
    reused = accept(again, csrf, token, password="Another-Passw0rd-2026")
    assert reused.status_code == 400
    assert reused.json()["code"] == "INVITATION_INVALID"


@pytest.mark.django_db
def test_all_bad_links_look_the_same(invited_user):
    _, invitation = invited_user
    client, csrf = public_client()
    good = make_token(invitation)

    expired = Invitation.objects.create(
        user=User.objects.create_user(email="late@synthetic.test", display_name="Late"),
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    candidates = ["not-a-token", good[:-2] + "xx", make_token(expired)]
    details = set()
    for token in candidates:
        response = client.post(
            "/api/v1/auth/invitations/inspect/",
            {"token": token},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 400
        assert response.json()["code"] == "INVITATION_INVALID"
        details.add(response.json()["detail"])
    assert len(details) == 1


@pytest.mark.django_db
def test_weak_password_is_rejected_and_link_stays_valid(invited_user):
    _, invitation = invited_user
    client, csrf = public_client()
    response = accept(client, csrf, make_token(invitation), password="short")
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert {error["field"] for error in body["errors"]} == {"password"}
    invitation.refresh_from_db()
    assert invitation.status == "open"


@pytest.mark.django_db
def test_resending_revokes_the_previous_link(invited_user):
    user, first = invited_user
    second = issue_invitation(user=user)
    first.refresh_from_db()
    assert first.status == "revoked"
    assert Invitation.objects.filter(user=user, accepted_at=None, revoked_at=None).get() == second

    client, csrf = public_client()
    assert accept(client, csrf, make_token(first)).status_code == 400
    assert accept(client, csrf, make_token(second)).status_code == 200


@pytest.mark.django_db
def test_suspended_or_terminated_user_cannot_activate(invited_user):
    user, invitation = invited_user
    user.is_active = False
    user.save(update_fields=["is_active"])
    client, csrf = public_client()
    assert accept(client, csrf, make_token(invitation)).status_code == 400
    assert AuditEvent.objects.filter(
        action=AuditAction.USER_INVITATION_REJECTED, outcome=AuditEvent.Outcome.FAILURE
    ).exists()


@pytest.mark.django_db
def test_activation_requires_csrf_token(invited_user):
    _, invitation = invited_user
    client = APIClient(enforce_csrf_checks=True)
    response = client.post(
        "/api/v1/auth/invitations/accept/",
        {"token": make_token(invitation), "password": NEW_PASSWORD},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_can_resend_invitation_via_api(client_for, admin_user):
    client = client_for(admin_user)
    staff_id = client.post("/api/v1/staff/", DOCTOR, format="json").json()["id"]
    drain_outbox()

    response = client.post(f"/api/v1/staff/{staff_id}/invitation/")
    assert response.status_code == 202
    assert response.json()["email"] == "new.doctor@synthetic.test"
    drain_outbox()
    assert len(mail.outbox) == 2
    assert Invitation.objects.filter(user__email="new.doctor@synthetic.test").count() == 2


@pytest.mark.django_db
def test_resend_rules(client_for, admin_user, make_user):
    client = client_for(admin_user)
    no_login = client.post(
        "/api/v1/staff/", {**DOCTOR, "email": None, "employee_number": "EMP-INV-2"}, format="json"
    ).json()["id"]
    response = client.post(f"/api/v1/staff/{no_login}/invitation/")
    assert response.status_code == 409
    assert response.json()["code"] == "NO_LOGIN"

    staff_id = client.post("/api/v1/staff/", DOCTOR, format="json").json()["id"]
    assert client_for(make_user()).post(f"/api/v1/staff/{staff_id}/invitation/").status_code == 403

    activated = User.objects.get(email="new.doctor@synthetic.test")
    activated.set_password(NEW_PASSWORD)
    activated.save()
    already = client.post(f"/api/v1/staff/{staff_id}/invitation/")
    assert already.status_code == 409
    assert already.json()["code"] == "ALREADY_ACTIVATED"


@pytest.mark.django_db
def test_admin_console_action_sends_invitation(admin_user, organization):
    user = User.objects.create_user(email="console@synthetic.test", display_name="Console")
    console = Client()
    console.force_login(admin_user)
    response = console.post(
        "/admin/identity/user/",
        {"action": "send_invitation", "_selected_action": [str(user.pk)]},
    )
    assert response.status_code == 302
    drain_outbox()
    assert mail.outbox[-1].to == ["console@synthetic.test"]
    assert AuditEvent.objects.filter(
        action=AuditAction.USER_INVITATION_ISSUED, resource_id=str(user.pk)
    ).exists()
