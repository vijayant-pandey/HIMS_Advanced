"""Phase 1 security review (spec 13, 13.5, 23; HIMS-SEC-011): each finding's fix, the spec 13.5
cases this review added tests for, and the review's own screen. All data is synthetic."""

import ast
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.apps import apps as django_apps
from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.compliance import encryption, security_review
from apps.facilities.models import Department
from apps.identity import session_limits
from apps.identity.models import MfaDevice, UserSession
from apps.organizations.dates import hospital_today
from apps.staff.models import (
    Designation,
    StaffCredential,
    StaffDepartmentAssignment,
    StaffDocument,
    StaffMember,
)
from common import crypto
from common.outbox.dispatcher import process_event
from common.outbox.models import OutboxEvent, ProcessedEvent

API = "/api/v1"
ME = f"{API}/auth/me/"
LOGIN = f"{API}/auth/login/"
PASSWORD = "Synthetic-Review-Passw0rd-2611"
PDF = b"%PDF-1.4\n% synthetic test document\n%%EOF\n"
BACKGROUND = {"HTTP_X_HIMS_BACKGROUND": "1"}


@pytest.fixture(autouse=True)
def _fresh_counts():
    cache.clear()  # sign-in counts and rate limits start at zero in every test


def _at(seconds_from_now: float):
    return patch(
        "apps.identity.session_limits._now",
        return_value=session_limits._now() + seconds_from_now,
    )


# --- F-01: sessions -------------------------------------------------------------------------


@pytest.mark.django_db
def test_background_refreshes_do_not_keep_a_session_awake(client_for, admin_user):
    idle = settings.SESSION_COOKIE_AGE
    wall_screen = client_for(admin_user)
    with _at(idle - 60):
        assert wall_screen.get(ME, **BACKGROUND).status_code == 200  # refreshing itself
    with _at(idle + 60):
        assert wall_screen.get(ME, **BACKGROUND).status_code == 401  # nobody used it
    entry = UserSession.objects.get(user=admin_user)
    assert entry.end_reason == UserSession.EndReason.EXPIRED
    event = AuditEvent.objects.get(action=AuditAction.AUTH_SESSIONS_ENDED)
    assert event.metadata == {"reason": "expired_idle", "sessions_ended": 1}

    in_use = client_for(admin_user)
    with _at(idle - 60):
        assert in_use.get(ME).status_code == 200  # a person clicked
    with _at(idle + 60):
        assert in_use.get(ME, **BACKGROUND).status_code == 200


@pytest.mark.django_db
def test_nobody_stays_signed_in_past_the_time_limit(client_for, admin_user):
    client = client_for(admin_user)
    step = settings.SESSION_COOKIE_AGE - 60
    elapsed = 0
    while elapsed + step < settings.HIMS_SESSION_MAX_SECONDS:
        elapsed += step
        with _at(elapsed):
            assert client.get(ME).status_code == 200  # in use all day
    with _at(settings.HIMS_SESSION_MAX_SECONDS + 60):
        assert client.get(ME).status_code == 401
    event = AuditEvent.objects.get(action=AuditAction.AUTH_SESSIONS_ENDED)
    assert event.metadata["reason"] == "expired_time_limit"


# --- F-02: password guessing -----------------------------------------------------------------


def _sign_in(email, password, address):
    return APIClient().post(
        LOGIN, {"email": email, "password": password}, format="json", REMOTE_ADDR=address
    )


@pytest.mark.django_db
def test_wrong_passwords_pause_sign_in_for_that_email_from_any_address(make_user):
    person = make_user(email="guess.target@synthetic.test", password=PASSWORD)
    for n in range(settings.HIMS_SIGN_IN_MAX_FAILURES):
        wrong = _sign_in(person.email, "Wrong-Guess-0000", f"10.1.0.{n + 1}")
        assert wrong.json()["code"] == "INVALID_CREDENTIALS"
    paused = _sign_in(person.email, PASSWORD, "10.2.0.1")  # right password, new address
    assert paused.status_code == 429
    assert paused.json()["code"] == "SIGN_IN_PAUSED"

    # An email without an account gets exactly the same answers, so nothing is revealed.
    for n in range(settings.HIMS_SIGN_IN_MAX_FAILURES):
        _sign_in("nobody.here@synthetic.test", "Wrong-Guess-0000", f"10.3.0.{n + 1}")
    stranger = _sign_in("nobody.here@synthetic.test", PASSWORD, "10.4.0.1")
    assert (stranger.status_code, stranger.json()["code"]) == (429, "SIGN_IN_PAUSED")

    cache.clear()  # the pause runs out
    assert _sign_in(person.email, PASSWORD, "10.5.0.1").status_code == 200


@pytest.mark.django_db
def test_console_sign_in_shares_the_per_account_pause(make_user, system_roles):
    admin = make_user(
        role=system_roles["organization-administrator"],
        email="console.target@synthetic.test",
        password=PASSWORD,
    )
    for n in range(settings.HIMS_SIGN_IN_MAX_FAILURES):
        _sign_in(admin.email, "Wrong-Guess-0000", f"10.6.0.{n + 1}")
    page = Client().post("/admin/login/", {"username": admin.email, "password": PASSWORD})
    assert page.status_code == 200  # the form again, not signed in
    assert "Sign-in is paused" in page.content.decode()
    assert "_auth_user_id" not in Client().session


# --- F-03: encryption keys -------------------------------------------------------------------


@pytest.mark.django_db
def test_old_encryption_keys_can_be_retired_after_rotation(make_user):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    with override_settings(HIMS_FIELD_ENCRYPTION_KEYS=[old]):
        device = MfaDevice.objects.create(
            user=make_user(), secret_encrypted=crypto.encrypt("synthetic-authenticator-secret")
        )
    with override_settings(HIMS_FIELD_ENCRYPTION_KEYS=[new, old]):
        before = encryption.status()
        assert before["keys"] == 2
        assert before["on_older_keys"] == 1
        assert encryption.rotate(dry_run=True) == {
            "Authenticator app secrets": 1,
            "Messages not yet delivered": 0,
        }
        assert encryption.status()["on_older_keys"] == 1  # a dry run changes nothing
        encryption.rotate()
        assert encryption.status()["on_older_keys"] == 0
        assert encryption.rotate()["Authenticator app secrets"] == 0  # repeating is harmless
    with override_settings(HIMS_FIELD_ENCRYPTION_KEYS=[new]):  # the old key is gone
        device.refresh_from_db()
        assert crypto.decrypt(device.secret_encrypted) == "synthetic-authenticator-secret"
    assert AuditEvent.objects.filter(action=AuditAction.DATABASE_ENCRYPTION_ROTATED).count() == 2


def test_every_encrypted_column_is_rotated():
    listed = {(label, field) for label, field, _ in encryption.ENCRYPTED_FIELDS}
    found = {
        (f"{model._meta.app_label}.{model.__name__}", field.name)
        for model in django_apps.get_models()
        for field in model._meta.get_fields()
        if field.name.endswith("_encrypted")
    }
    assert found == listed


# --- F-04: audit log flooding ----------------------------------------------------------------


@pytest.mark.django_db
def test_no_access_reports_cannot_flood_the_audit_log(client_for, make_user, admin_user):
    newcomer = client_for(make_user())
    first = newcomer.post(f"{API}/auth/no-access-report/", {"page": "/"}, format="json")
    again = newcomer.post(f"{API}/auth/no-access-report/", {"page": "/"}, format="json")
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["reference"] == first.json()["reference"]
    assert AuditEvent.objects.filter(action=AuditAction.ACCESS_NONE_ASSIGNED).count() == 1

    has_access = client_for(admin_user).post(f"{API}/auth/no-access-report/", {}, format="json")
    assert (has_access.status_code, has_access.json()["code"]) == (409, "HAS_ACCESS")
    assert AuditEvent.objects.filter(action=AuditAction.ACCESS_NONE_ASSIGNED).count() == 1


# --- F-05 and spec 13.5 case 7: background jobs --------------------------------------------


@pytest.mark.django_db
def test_a_background_event_for_another_hospital_never_runs(organization):
    event = OutboxEvent.objects.create(
        event_type="staff.member.created",
        customer_id="another-hospital",
        aggregate_type="staff_member",
        aggregate_id=str(uuid.uuid4()),
        payload={},
    )
    # A message addressed to another deployment is refused before anything is read.
    process_event(event.pk, deployment="another-hospital")
    event.refresh_from_db()
    assert event.status == OutboxEvent.Status.PENDING

    # An event whose own hospital is not this deployment is stopped, with the reason.
    process_event(event.pk, deployment=settings.HIMS_DEPLOYMENT_ID)
    event.refresh_from_db()
    assert event.status == OutboxEvent.Status.DEAD
    assert "another-hospital" in event.last_error
    assert not ProcessedEvent.objects.filter(event_id=event.pk).exists()


# --- Spec 13.5 cases 1 and 6 -----------------------------------------------------------------


@pytest.mark.django_db
def test_a_record_or_session_from_another_hospital_is_not_found(client_for, admin_user):
    """Each hospital has its own database: an ID or a session from elsewhere is not here."""
    client = client_for(admin_user)
    assert client.get(f"{API}/facilities/{uuid.uuid4()}/").status_code == 404
    stranger = APIClient()
    stranger.cookies[settings.SESSION_COOKIE_NAME] = "s" * 32  # a session made elsewhere
    assert stranger.get(ME).status_code == 401


@pytest.mark.django_db
def test_a_guessed_document_address_finds_nothing(
    client_for, admin_user, make_user, system_roles, facility_a, facility_b, organization
):
    elsewhere = Department.objects.create(
        organization=organization,
        facility=facility_b,
        code="review-b",
        name="Review B",
        department_type=Department.DepartmentType.CLINICAL,
    )
    nurse = StaffMember.objects.create(
        organization=organization,
        employee_number="EMP-REVIEW-1",
        given_name="Guess",
        family_name="Target",
        staff_type="nurse",
        joined_on="2026-01-05",
    )
    StaffDepartmentAssignment.objects.create(
        organization=organization,
        staff=nurse,
        department=elsewhere,
        designation=Designation.objects.first(),
        valid_from=hospital_today() - timedelta(days=30),
    )
    licence = StaffCredential.objects.create(
        organization=organization,
        staff=nurse,
        credential_type="nursing_registration",
        registration_number="KNC-REVIEW",
        issuing_authority="Karnataka Nursing Council",
        jurisdiction="IN-KA",
        expires_at=hospital_today() + timedelta(days=400),
    )
    uploaded = client_for(admin_user).post(
        f"{API}/staff/{nurse.pk}/documents/",
        {"file": SimpleUploadedFile("licence.pdf", PDF), "credential": licence.pk},
        format="multipart",
    )
    assert uploaded.status_code == 201
    document = StaffDocument.objects.get()

    # HR for facility A holds the document permission, but not where this nurse works.
    hr_a = client_for(make_user(role=system_roles["hr-credentialing-officer"], facility=facility_a))
    assert hr_a.get(f"{API}/staff-documents/{document.pk}/download/").status_code == 404
    assert hr_a.get(f"{API}/staff-documents/{uuid.uuid4()}/download/").status_code == 404
    downloads = AuditEvent.objects.filter(action=AuditAction.STAFF_DOCUMENT_DOWNLOADED)
    assert not downloads.exists()


# --- The review itself ----------------------------------------------------------------------


@pytest.mark.django_db
def test_security_review_tab_and_console_page(client_for, auditor_user, admin_user, make_user):
    body = client_for(auditor_user).get(f"{API}/security/review/").json()
    assert [finding["code"] for finding in body["findings"]] == [
        code for code, *_ in security_review.FINDINGS
    ]
    assert len(body["cases"]) == 10
    assert body["encryption"]["on_older_keys"] == 0
    assert client_for(make_user()).get(f"{API}/security/review/").status_code == 403

    console = Client()
    console.force_login(admin_user)
    page = console.get("/admin/compliance/consoleaccessblock/security-status/").content.decode()
    for expected in ("Security review", "Encryption keys for stored secrets", "F-01"):
        assert expected in page, expected


def test_review_evidence_points_at_real_tests():
    backend = Path(settings.BASE_DIR)
    named = [test for *_, tests in security_review.FINDINGS for test in tests]
    named += [test for *_, tests in security_review.SPEC_CASES for test in tests]
    for test in named:
        path, name = test.split("::")
        tree = ast.parse((backend / path).read_text(encoding="utf-8"))
        functions = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        assert name in functions, test
