"""The log safety net, rule by rule (HIMS-SEC-019; spec 13.3, 13.5, 27.2). Synthetic data.

The end-to-end check that real flows leak nothing is test_secrets_never_logged.py.
"""

import importlib
import io
import json
import logging
from pathlib import Path

import pytest
import yaml
from django.apps import apps as django_apps
from django.core.mail import EmailMessage
from django.test import RequestFactory, override_settings

from apps.notifications.backends import ConsoleEmailBackend, ConsoleSmsBackend
from apps.notifications.models import Notification
from common import crypto
from common.log_safety import (
    HIDDEN,
    hidden_parts,
    is_sensitive_key,
    known_secrets,
    scrub,
    scrub_value,
)
from common.logging import JsonFormatter
from config.celery import app as celery_app

SMTP_PASSWORD = "Synthetic-Smtp-Passw0rd-2001"
CHAIN_SECRET = "synthetic-chain-secret-" + "7" * 20
ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    ("line", "kept", "gone"),
    [
        ("GET /api/v1/patients/?search=Asha+Rao&page=2", "/api/v1/patients/?search=", "Asha"),
        ("sent http://app.test/reset-password#token=Abc.123-x", "#token=[hidden]", "Abc.123"),
        ("connect postgres://hims:p@ss@w0rd@db:5432/hims", "@db:5432/hims", "w0rd"),
        ("Authorization: Bearer eyJhbGciOi.abc.def", "Authorization", "eyJhbGciOi"),
        ("{'password': 'Synthetic-X Passw0rd'}", "'password': '[hidden]'", "Passw0rd"),
        ('token=xyz123 api_key: K12345 secret="a b"', "api_key: [hidden]", "K12345"),
        ("refused to=+91 98000 19051 ok", "refused to=", "19051"),
        ("text='Asha Rao' was refused", "text='[hidden]'", "Asha"),
        ("display_name=Asha patient_id=p-7", "patient_id=p-7", "Asha"),
        ("could not reach asha.rao@synthetic.test", "could not reach", "asha.rao"),
        (
            "DETAIL:  Key (lower(email::text))=(asha@synthetic.test) already exists.",
            "Key (lower(email::text))=([hidden]) already exists",
            "asha@",
        ),
        (
            "DETAIL:  Key (staff_id, during)=(5, [08:00,20:00)) conflicts with existing "
            "key (staff_id, during)=(5, [12:00,16:00)).",
            "conflicts with existing key (staff_id, during)=([hidden])",
            "12:00",
        ),
        (
            "DETAIL:  Failing row contains (1, Asha, Rao, 1990-01-01).",
            "contains ([hidden])",
            "Asha",
        ),
    ],
)
def test_secrets_and_personal_details_in_text_are_hidden(line, kept, gone):
    cleaned = scrub(line)
    assert kept in cleaned and gone not in cleaned and HIDDEN in cleaned


@pytest.mark.parametrize(
    "line",
    [
        "Forbidden: /api/v1/auth/password-reset/confirm/",
        "Account deactivated; sessions ended",
        "Outbox event exhausted publish retries",
        "Task outbox.handle_event[6b1c] succeeded in 0.1s: None",
    ],
)
def test_ordinary_lines_are_left_alone(line):
    assert scrub(line) == line


@override_settings(EMAIL_HOST_PASSWORD=SMTP_PASSWORD, HIMS_AUDIT_CHAIN_KEYS=[f"k1:{CHAIN_SECRET}"])
def test_the_deployments_own_secrets_are_hidden_wherever_they_appear():
    assert SMTP_PASSWORD in known_secrets() and CHAIN_SECRET in known_secrets()
    assert scrub(f"login failed for {SMTP_PASSWORD}!") == f"login failed for {HIDDEN}!"
    assert scrub(f"chain {CHAIN_SECRET}") == f"chain {HIDDEN}"


def test_short_or_harmless_settings_are_not_treated_as_secrets():
    secrets = known_secrets()
    assert "django.contrib.auth.hashers.PBKDF2PasswordHasher" not in secrets
    assert all(len(secret) >= 8 for secret in secrets)


def test_fields_named_like_secrets_or_payloads_are_hidden_others_kept():
    request = RequestFactory().post("/api/v1/auth/login/?search=Asha", {"password": "x"})
    cleaned = scrub_value(
        None,
        {
            "password": "Synthetic-Log-Passw0rd-2004",
            "nested": {"recovery_codes": ["a1b2"], "api_key": "k"},
            "args": ["patient-id"],
            "request": request,
            "sessions_ended": 2,
            "status_code": 500,
            "credential_id": "c-1",
            "patient_id": "p-1",
            "email": "asha@synthetic.test",
            "note": "see https://x.test/?q=Asha",
        },
    )
    assert cleaned == {
        "password": HIDDEN,
        "nested": {"recovery_codes": HIDDEN, "api_key": HIDDEN},
        "args": HIDDEN,
        "request": "POST /api/v1/auth/login/",
        "sessions_ended": 2,
        "status_code": 500,
        "credential_id": "c-1",
        "patient_id": "p-1",
        "email": HIDDEN,
        "note": HIDDEN,
    }


def test_the_json_formatter_hides_secrets_in_message_fields_and_traceback():
    try:
        raise ValueError("provider said token=Abc123456 for +919800019051")
    except ValueError as exc:
        record = logging.makeLogRecord(
            {
                "name": "hims.test",
                "levelno": logging.ERROR,
                "levelname": "ERROR",
                "msg": "call failed: %s",
                "args": ("https://sms.test/send?to=+919800019051",),
                "exc_info": (type(exc), exc, exc.__traceback__),
                "password": "Synthetic-Log-Passw0rd-2004",
                "status_code": 502,
            }
        )
    line = JsonFormatter().format(record)
    payload = json.loads(line)
    assert "Abc123456" not in line and "9800019051" not in line and "Passw0rd" not in line
    assert payload["message"] == f"call failed: https://sms.test/send?to={HIDDEN}"
    assert payload["password"] == HIDDEN and payload["status_code"] == 502
    assert "ValueError: provider said token=[hidden]" in payload["exception"]


def test_hidden_parts_finds_what_the_readable_copy_hides():
    readable = f"Open http://a.test/#token={HIDDEN} now; code {HIDDEN}."
    assert hidden_parts(readable, "Open http://a.test/#token=SEC1 now; code 482913.") == [
        "SEC1",
        "482913",
    ]
    assert hidden_parts("plain", "plain") == []
    assert hidden_parts(f"a {HIDDEN} b", "something else entirely") is None


def test_celery_workers_keep_the_safe_json_logging():
    assert celery_app.conf.worker_hijack_root_logger is False


# --- Messages printed to the server output ---------------------------------------------------


def test_console_sms_prints_everything_on_a_developer_pc(capsys):
    ConsoleSmsBackend().send("+919800019051", "Your code is 482913")
    assert "Your code is 482913" in capsys.readouterr().out


@override_settings(HIMS_ENVIRONMENT="staging")
def test_console_sms_on_a_server_prints_neither_text_nor_number(capsys):
    ConsoleSmsBackend().send("+919800019051", "Your code is 482913")
    out = capsys.readouterr().out
    assert "482913" not in out and "9800019051" not in out and "+91…51" in out


@override_settings(HIMS_ENVIRONMENT="staging")
def test_console_email_on_a_server_hides_the_sign_in_link():
    stream = io.StringIO()
    message = EmailMessage(
        "Reset your password",
        "Open http://app.test/reset-password#token=Synthetic-Link-Secret-2002 within an hour.",
        to=["asha@synthetic.test"],
    )
    ConsoleEmailBackend(stream=stream).send_messages([message])
    out = stream.getvalue()
    assert "Synthetic-Link-Secret-2002" not in out and "asha@" not in out
    assert "#token=[hidden] within an hour" in out


# --- Stored error texts ----------------------------------------------------------------------


@pytest.mark.django_db
def test_old_error_texts_are_cleaned_by_the_migration():
    real = "Open http://app.test/activate#token=Synthetic-Old-Secret-2003 to start."
    failed = Notification.objects.create(
        channel="email",
        category="security",
        template="identity.invitation",
        recipients=["asha@synthetic.test"],
        subject="Welcome",
        body=f"Open http://app.test/activate#token={HIDDEN} to start.",
        body_encrypted=crypto.encrypt(real),
        status="failed",
        last_error=f"SMTPDataError: (554, 'refused: {real}')",
    )
    harmless = Notification.objects.create(
        channel="email",
        category="security",
        template="identity.invitation",
        recipients=["ravi@synthetic.test"],
        subject="Welcome",
        body="Hello",
        status="failed",
        last_error="ConnectionRefusedError: [Errno 111] Connection refused",
    )
    migration = importlib.import_module("apps.notifications.migrations.0002_scrub_last_errors")
    migration.scrub_last_errors(django_apps, None)
    failed.refresh_from_db()
    harmless.refresh_from_db()
    assert "Synthetic-Old-Secret-2003" not in failed.last_error
    assert failed.last_error.startswith("SMTPDataError: (554, 'refused: Open http://app.test/")
    assert harmless.last_error == "ConnectionRefusedError: [Errno 111] Connection refused"


# --- Secrets never travel in a web address ---------------------------------------------------


def test_no_api_takes_a_secret_in_the_address():
    """Web addresses end up in load-balancer, proxy and browser logs (spec 13.3 "minimize
    sensitive data in … URLs"): passwords, sign-in tokens and codes go in the request body."""
    schema = yaml.safe_load((ROOT / "docs" / "api" / "openapi.yaml").read_text(encoding="utf-8"))
    in_address = [
        f"{method.upper()} {path} ?{parameter['name']}"
        for path, operations in schema["paths"].items()
        for method, operation in operations.items()
        if isinstance(operation, dict)
        for parameter in operation.get("parameters", [])
        if parameter.get("in") == "query" and is_sensitive_key(parameter["name"])
    ]
    assert in_address == []
