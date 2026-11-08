"""Security test (spec 13.5 "an integration logs a secret or sensitive patient data during an
exception"; 13.3, 27.2; HIMS-SEC-019): no password, sign-in link, two-factor code, key or patient
detail ever reaches a log line, the server output, a stored error text or the audit log.

The real flows run with marked synthetic secrets while every log line is captured at DEBUG level
and written by the production formatter; then each secret is looked for everywhere. A failure
names the secret (its label, never its value) and where it was found. All data is synthetic.
"""

import json
import logging
import re
import smtplib

import pytest
from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.core.mail.backends.base import BaseEmailBackend
from django.db import IntegrityError, transaction
from django.test import override_settings
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.identity import mfa
from apps.identity.api.views import CurrentUserView
from apps.identity.models import MfaDevice, User
from apps.notifications.models import Notification
from common import crypto
from common.logging import JsonFormatter
from common.outbox.dispatcher import dispatch_pending, process_event
from common.outbox.models import OutboxEvent
from common.request_context import RequestContextLogFilter

API = "/api/v1"
PASSWORD = "Synthetic-Canary-Passw0rd-1901"
WRONG_PASSWORD = "Synthetic-Wrong-Passw0rd-1902"
NEW_PASSWORD = "Synthetic-Renewed-Passw0rd-1903"
INVITED_PASSWORD = "Synthetic-Invited-Passw0rd-1904"
PATIENT_NAME = "Canarypatient Zyxwvut"
PATIENT_PHONE = "+919800019051"
PROVIDER_KEY = "sk_live_canary_19060000000000"
LINK = re.compile(r"#token=(\S+)")


class _Lines(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []
        self.setFormatter(JsonFormatter())
        self.addFilter(RequestContextLogFilter())

    def emit(self, record):
        self.lines.append(self.format(record))


class RefusingEmailBackend(BaseEmailBackend):
    """An email provider that refuses the message and repeats it in its error, as some do."""

    def send_messages(self, messages):
        raise smtplib.SMTPDataError(554, f"Message refused: {messages[0].body}")


@pytest.fixture
def log_lines():
    handler, root = _Lines(), logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield handler.lines
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)


def drain_outbox() -> None:
    while dispatch_pending(publish=lambda event: process_event(event.pk)):
        pass


def public_client() -> tuple[APIClient, str]:
    client = APIClient(enforce_csrf_checks=True)
    client.get(f"{API}/auth/csrf/")
    return client, client.cookies["hims_csrftoken"].value


def link_token(text: str) -> str:
    match = LINK.search(text)
    assert match, "no sign-in link in the message"
    return match.group(1)


def leaks(secrets: dict[str, str], places: dict[str, str]) -> list[str]:
    return [
        f"{label} in {place}"
        for label, secret in secrets.items()
        for place, text in places.items()
        if secret and secret in text
    ]


@pytest.mark.django_db
def test_no_secret_reaches_a_log_the_audit_log_or_a_stored_error(
    log_lines, capsys, client_for, make_user, system_roles, monkeypatch
):
    cache.clear()  # fresh sign-in rate limits
    secrets = {
        "password": PASSWORD,
        "wrong password": WRONG_PASSWORD,
        "new password": NEW_PASSWORD,
        "invited person's password": INVITED_PASSWORD,
        "patient name": PATIENT_NAME,
        "patient phone": PATIENT_PHONE,
        "provider key": PROVIDER_KEY,
        "Django secret key": settings.SECRET_KEY,
        "database password": settings.DATABASES["default"].get("PASSWORD") or "",
    }
    admin = make_user(role=system_roles["organization-administrator"])
    nurse = make_user(role=system_roles["basic-staff"], password=PASSWORD)

    # 1. Signing in: a wrong password, the right one, two-factor set-up and backup codes.
    device = APIClient()
    sign_in = {"email": nurse.email, "password": WRONG_PASSWORD}
    assert device.post(f"{API}/auth/login/", sign_in, format="json").status_code in (400, 401)
    sign_in["password"] = PASSWORD
    assert device.post(f"{API}/auth/login/", sign_in, format="json").status_code == 200
    setup = device.post(f"{API}/auth/mfa/setup/")
    assert setup.status_code == 201
    secrets["authenticator secret"] = setup.json()["secret"]
    stored = crypto.decrypt(MfaDevice.objects.get(user=nurse).secret_encrypted)
    code = mfa.totp(stored, mfa.current_step())
    confirmed = device.post(f"{API}/auth/mfa/confirm/", {"code": code}, format="json")
    assert confirmed.status_code == 200
    recovery = confirmed.json()["recovery_codes"]
    secrets.update({f"backup code {n}": value for n, value in enumerate(recovery, 1)})
    device.post(f"{API}/auth/logout/")
    device = APIClient()
    device.post(f"{API}/auth/login/", sign_in, format="json")
    device.post(f"{API}/auth/login/verify/", {"code": "000000"}, format="json")
    verified = device.post(f"{API}/auth/login/verify/", {"code": recovery[0]}, format="json")
    assert verified.status_code == 200

    # 2. Forgotten password: the reset link, then the new password.
    public, csrf = public_client()
    public.post(
        f"{API}/auth/password-reset/request/",
        {"email": nurse.email},
        format="json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    drain_outbox()
    secrets["reset link"] = link_token(mail.outbox[-1].body)
    public, csrf = public_client()
    reset = public.post(
        f"{API}/auth/password-reset/confirm/",
        {"token": secrets["reset link"], "password": NEW_PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert reset.status_code == 204

    # 3. A new member of staff: the activation link, then their first password.
    new_staff = {
        "email": "canary.invitee@synthetic.test",
        "employee_number": "EMP-CANARY-1",
        "given_name": "Canary",
        "family_name": "Invitee",
        "staff_type": "nurse",
        "joined_on": "2026-02-01",
    }
    assert client_for(admin).post(f"{API}/staff/", new_staff, format="json").status_code == 201
    drain_outbox()
    secrets["activation link"] = link_token(mail.outbox[-1].body)
    public, csrf = public_client()
    accepted = public.post(
        f"{API}/auth/invitations/accept/",
        {"token": secrets["activation link"], "password": INVITED_PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert accepted.status_code == 200, accepted.json()

    # 4. An email provider refuses a message and repeats it, sign-in link included, in its error.
    with override_settings(EMAIL_BACKEND=f"{__name__}.RefusingEmailBackend"):
        public, csrf = public_client()
        public.post(
            f"{API}/auth/password-reset/request/",
            {"email": "canary.invitee@synthetic.test"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        drain_outbox()
    refused = Notification.objects.filter(status="failed").latest("created_at")
    secrets["refused reset link"] = link_token(crypto.decrypt(refused.body_encrypted))
    assert refused.last_error.startswith("SMTPDataError: ")  # the kind of error is kept
    shown = client_for(admin).get(f"{API}/notifications/{refused.pk}/")
    assert shown.status_code == 200

    # 5. An integration fails during a request: the error repeats what it was sent.
    def failing_call(view, request):
        raise RuntimeError(
            f"SMS gateway refused to={PATIENT_PHONE} text='{PATIENT_NAME}' "
            f"api_key={PROVIDER_KEY} via postgres://hims:{secrets['database password']}@db/hims "
            f"(signing key {settings.SECRET_KEY})"
        )

    monkeypatch.setattr(CurrentUserView, "get", failing_call)
    crashed = client_for(admin).get(
        f"{API}/auth/me/",
        {"search": PATIENT_NAME, "token": secrets["reset link"]},
        HTTP_AUTHORIZATION=f"Bearer {PROVIDER_KEY}",
    )
    assert crashed.status_code == 500
    assert crashed.json()["code"] == "INTERNAL_ERROR"  # and nothing of the error is shown

    # 6. The database refuses a row and names the values in its error.
    # (In a variable: a traceback quotes source lines, and real code never holds a person's email.)
    secrets["patient email"] = email = "canary.patient@synthetic.test"
    User.objects.create_user(email=email, display_name=PATIENT_NAME)
    try:
        with transaction.atomic():
            # Straight to the database, past the form check that would catch it first.
            User.objects.bulk_create([User(email=email, display_name="Duplicate")])
    except IntegrityError:
        logging.getLogger("hims.test").exception("Could not save the person")
    else:  # pragma: no cover - the database must refuse the duplicate
        pytest.fail("duplicate email was accepted")

    # The flows really logged (so an empty search would not pass by accident) …
    logged = "\n".join(log_lines)
    assert "Unhandled API exception" in logged and "RuntimeError" in logged
    assert "notification_failed" in logged and "Could not save the person" in logged
    assert "IntegrityError" in logged and "[hidden]" in logged
    output = capsys.readouterr()
    # … and no secret is anywhere.
    places = {
        "the logs": logged,
        "the server output": output.out + output.err,
        "the audit log": json.dumps(list(AuditEvent.objects.values()), default=str),
        "the stored email copies and errors": json.dumps(
            list(Notification.objects.values("subject", "body", "last_error")), default=str
        ),
        "the outbox": json.dumps(list(OutboxEvent.objects.values("payload")), default=str),
        "the error shown to the administrator": shown.content.decode(),
        "the error shown to the caller": crashed.content.decode(),
    }
    found = leaks(secrets, places)
    assert not found, "Leaked: " + "; ".join(found)
