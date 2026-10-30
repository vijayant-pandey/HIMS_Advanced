"""Licence documents and expiry alerts (HIMS-STAFF-005/006). All data is synthetic."""

from datetime import date, timedelta
from pathlib import Path

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, override_settings
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.staff import expiry
from apps.staff.models import (
    CredentialExpiryAlert,
    QualificationType,
    StaffCredential,
    StaffDocument,
    StaffMember,
    StaffQualification,
)

API = "/api/v1"
PDF = b"%PDF-1.4\n% synthetic test document\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture
def nurse(organization, make_user):
    return StaffMember.objects.create(
        organization=organization,
        user=make_user(email="nurse.docs@synthetic.test", display_name="Nurse Docs"),
        employee_number="EMP-DOC-1",
        given_name="Mary",
        family_name="Docs",
        staff_type="nurse",
        joined_on="2026-01-05",
    )


def _licence(staff, expires_at, number="KNC-1", **extra):
    return StaffCredential.objects.create(
        organization_id=staff.organization_id,
        staff=staff,
        credential_type="nursing_registration",
        registration_number=number,
        issuing_authority="Karnataka Nursing Council",
        jurisdiction="IN-KA",
        expires_at=expires_at,
        **extra,
    )


def _upload(client, staff, content=PDF, name="licence.pdf", **target):
    return client.post(
        f"{API}/staff/{staff.pk}/documents/",
        {"file": SimpleUploadedFile(name, content), **target},
        format="multipart",
    )


# --- Documents --------------------------------------------------------------------------------


@pytest.mark.django_db
def test_upload_stores_safely_and_is_audited(client_for, admin_user, nurse):
    licence = _licence(nurse, date(2027, 1, 1))
    response = _upload(
        client_for(admin_user), nurse, name="..\\..\\Mary Docs licence.PDF", credential=licence.pk
    )
    assert response.status_code == 201, response.json()
    row = response.json()
    assert row["original_name"] == "Mary Docs licence.PDF"  # no folder parts kept
    assert row["content_type"] == "application/pdf"
    assert row["size_bytes"] == len(PDF)
    document = StaffDocument.objects.get(pk=row["id"])
    stored = Path(document.file.name)
    assert stored.parts[:2] == ("staff-documents", str(nurse.pk))
    assert "Mary" not in stored.name  # random name on disk
    assert len(document.sha256) == 64
    event = AuditEvent.objects.get(action=AuditAction.STAFF_DOCUMENT_UPLOADED)
    assert event.metadata["sha256"] == document.sha256


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("content", "name", "message"),
    [
        (b"MZ\x90\x00 not really a pdf", "licence.pdf", "Only PDF, JPG or PNG"),
        (b"", "empty.pdf", "empty"),
    ],
)
def test_wrong_or_empty_files_are_refused(client_for, admin_user, nurse, content, name, message):
    licence = _licence(nurse, date(2027, 1, 1))
    response = _upload(
        client_for(admin_user), nurse, content=content, name=name, credential=licence.pk
    )
    assert response.status_code == 400
    assert message in str(response.json())
    assert StaffDocument.objects.count() == 0


@pytest.mark.django_db
@override_settings(HIMS_UPLOAD_MAX_BYTES=10)
def test_too_large_files_are_refused(client_for, admin_user, nurse):
    licence = _licence(nurse, date(2027, 1, 1))
    response = _upload(client_for(admin_user), nurse, credential=licence.pk)
    assert response.status_code == 400
    assert "too large" in str(response.json())


@pytest.mark.django_db
def test_document_must_belong_to_one_of_this_persons_records(
    client_for, admin_user, nurse, organization
):
    client = client_for(admin_user)
    assert _upload(client, nurse).status_code == 400  # neither
    other = StaffMember.objects.create(
        organization=organization,
        employee_number="EMP-OTHER",
        given_name="O",
        family_name="Ther",
        staff_type="doctor",
        joined_on="2026-01-01",
    )
    foreign = _licence(other, date(2027, 1, 1), number="KMC-9")
    assert _upload(client, nurse, credential=foreign.pk).status_code == 404


@pytest.mark.django_db
def test_download_is_audited_and_never_runs_content(client_for, admin_user, nurse):
    licence = _licence(nurse, date(2027, 1, 1))
    client = client_for(admin_user)
    document_id = _upload(
        client, nurse, content=PNG, name="scan.png", credential=licence.pk
    ).json()["id"]
    response = client.get(f"{API}/staff-documents/{document_id}/download/")
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == PNG
    assert response["Content-Type"] == "image/png"
    assert response["Content-Disposition"].startswith("attachment;")
    assert "sandbox" in response["Content-Security-Policy"]
    assert response["Cache-Control"] == "private, no-store"
    inline = client.get(f"{API}/staff-documents/{document_id}/download/", {"inline": "true"})
    assert inline["Content-Disposition"].startswith("inline;")
    assert AuditEvent.objects.filter(action=AuditAction.STAFF_DOCUMENT_DOWNLOADED).count() == 2


@pytest.mark.django_db
def test_people_without_staff_access_cannot_open_documents(
    client_for, admin_user, nurse, make_user, system_roles
):
    licence = _licence(nurse, date(2027, 1, 1))
    document_id = _upload(client_for(admin_user), nurse, credential=licence.pk).json()["id"]
    basic = client_for(make_user(role=system_roles["basic-staff"]))
    assert basic.get(f"{API}/staff-documents/{document_id}/download/").status_code == 403


@pytest.mark.django_db
def test_archive_keeps_the_document(client_for, admin_user, nurse):
    licence = _licence(nurse, date(2027, 1, 1))
    client = client_for(admin_user)
    document_id = _upload(client, nurse, credential=licence.pk).json()["id"]
    url = f"{API}/staff-documents/{document_id}/archive/"
    archived = client.post(url, {"reason": "Wrong person's licence"}, format="json")
    assert archived.status_code == 200 and archived.json()["is_archived"] is True
    assert client.post(url, {"reason": "again"}, format="json").json()["code"] == "ALREADY_ARCHIVED"
    detail = client.get(f"{API}/staff/{nurse.pk}/").json()
    assert [d["archive_reason"] for d in detail["documents"]] == ["Wrong person's licence"]
    assert StaffDocument.objects.count() == 1


@pytest.mark.django_db
def test_qualification_documents(client_for, admin_user, nurse):
    qualification = StaffQualification.objects.create(
        organization_id=nurse.organization_id,
        staff=nurse,
        qualification_type=QualificationType.objects.filter(is_active=True).first(),
        institution="Synthetic College",
        year_awarded=2020,
    )
    response = _upload(client_for(admin_user), nurse, qualification=qualification.pk)
    assert response.status_code == 201
    assert response.json()["qualification"] == str(qualification.pk)


# --- Expiry alerts ----------------------------------------------------------------------------


def test_alert_stages():
    today = date(2026, 10, 29)
    assert expiry.stage_for(today + timedelta(days=90), today) is None
    assert expiry.stage_for(today + timedelta(days=60), today) == 60
    assert expiry.stage_for(today + timedelta(days=25), today) == 30  # catch-up after a gap
    assert expiry.stage_for(today + timedelta(days=7), today) == 7
    assert expiry.stage_for(today, today) == 7  # expires today: still the 7-day stage
    assert expiry.stage_for(today - timedelta(days=1), today) == 0


@pytest.mark.django_db
def test_daily_alerts_once_per_stage_to_hr_and_the_person(nurse, make_user, system_roles):
    hr = make_user(role=system_roles["hr-credentialing-officer"], email="hr@synthetic.test")
    today = timezone.localdate()
    licence = _licence(nurse, today + timedelta(days=25))

    assert expiry.send_credential_expiry_alerts(today) == 1
    recipients = sorted(address for message in mail.outbox for address in message.to)
    assert recipients == ["hr@synthetic.test", "nurse.docs@synthetic.test"]
    assert "expires on" in mail.outbox[0].body or "expires on" in mail.outbox[1].body

    mail.outbox.clear()
    assert expiry.send_credential_expiry_alerts(today) == 0  # same day again: nothing
    assert mail.outbox == []

    assert expiry.send_credential_expiry_alerts(today + timedelta(days=20)) == 1  # 7-day stage
    assert expiry.send_credential_expiry_alerts(today + timedelta(days=30)) == 1  # expired
    stages = sorted(
        CredentialExpiryAlert.objects.filter(credential=licence).values_list(
            "days_before", flat=True
        )
    )
    assert stages == [0, 7, 30]
    assert AuditEvent.objects.filter(action=AuditAction.CREDENTIAL_EXPIRY_ALERT_SENT).count() == 3
    assert hr.email in recipients


@pytest.mark.django_db
def test_renewed_licence_starts_alerts_again(nurse):
    today = timezone.localdate()
    licence = _licence(nurse, today + timedelta(days=5))
    expiry.send_credential_expiry_alerts(today)
    licence.expires_at = today + timedelta(days=400)  # renewed
    licence.save()
    assert expiry.send_credential_expiry_alerts(today) == 0
    licence.expires_at = today + timedelta(days=6)  # new expiry date, new alerts
    licence.save()
    assert expiry.send_credential_expiry_alerts(today) == 1


@pytest.mark.django_db
def test_no_alerts_for_staff_who_left_or_rejected_licences(nurse, organization):
    today = timezone.localdate()
    _licence(nurse, today + timedelta(days=3), verification_status="rejected")
    nurse.employment_status = "terminated"
    nurse.save()
    _licence(nurse, today + timedelta(days=3), number="KNC-2")
    assert expiry.send_credential_expiry_alerts(today) == 0


@pytest.mark.django_db
def test_management_command_sends_due_alerts(nurse):
    _licence(nurse, timezone.localdate() - timedelta(days=2))
    call_command("send_credential_expiry_alerts")
    assert CredentialExpiryAlert.objects.filter(days_before=0).count() == 1


# --- Licence expiry list ----------------------------------------------------------------------


@pytest.mark.django_db
def test_expiring_list_soonest_first_with_alert_info(client_for, admin_user, nurse):
    today = timezone.localdate()
    _licence(nurse, today + timedelta(days=40), number="KNC-A")
    expired = _licence(nurse, today - timedelta(days=3), number="KNC-B")
    _licence(nurse, today + timedelta(days=200), number="KNC-C")  # outside the window
    expiry.send_credential_expiry_alerts(today)
    client = client_for(admin_user)

    rows = client.get(f"{API}/staff-credentials/expiring/").json()
    assert [r["registration_number"] for r in rows] == ["KNC-B", "KNC-A"]
    first = rows[0]
    assert first["id"] == str(expired.pk)
    assert first["days_left"] == -3 and first["expiry_state"] == "expired"
    assert first["staff_name"] == "Mary Docs" and first["last_alert"] == "expired"
    future_only = client.get(
        f"{API}/staff-credentials/expiring/", {"include_expired": "false"}
    ).json()
    assert [r["registration_number"] for r in future_only] == ["KNC-A"]
    wider = client.get(f"{API}/staff-credentials/expiring/", {"within": 365}).json()
    assert len(wider) == 3


@pytest.mark.django_db
def test_expiring_list_needs_staff_access(client_for, make_user, system_roles):
    basic = client_for(make_user(role=system_roles["basic-staff"]))
    assert basic.get(f"{API}/staff-credentials/expiring/").status_code == 403


# --- Admin console and deploy check -----------------------------------------------------------


@pytest.mark.django_db
def test_admin_console_upload_uses_the_same_checks_and_archives(admin_user, nurse):
    licence = _licence(nurse, date(2027, 1, 1))
    console = Client()
    console.force_login(admin_user)
    bad = console.post(
        "/admin/staff/staffdocument/add/",
        {"staff": nurse.pk, "credential": licence.pk, "file": SimpleUploadedFile("x.pdf", b"nope")},
    )
    assert bad.status_code == 200 and b"Only PDF, JPG or PNG" in bad.content
    good = console.post(
        "/admin/staff/staffdocument/add/",
        {"staff": nurse.pk, "credential": licence.pk, "file": SimpleUploadedFile("ok.pdf", PDF)},
    )
    assert good.status_code == 302
    document = StaffDocument.objects.get()
    assert document.uploaded_by == admin_user and document.content_type == "application/pdf"
    console.post(
        f"/admin/staff/staffdocument/{document.pk}/change/",
        {"archive_reason_input": "Replaced by a clearer scan"},
    )
    document.refresh_from_db()
    assert document.archive_reason == "Replaced by a clearer scan"
    assert console.get("/admin/staff/credentialexpiryalert/").status_code == 200


@override_settings(HIMS_ENVIRONMENT="production")
def test_deploy_check_warns_about_local_document_storage():
    from apps.staff.checks import document_storage_is_durable

    warnings = document_storage_is_durable(None)
    assert [w.id for w in warnings] == ["hims.W001"]


@override_settings(HIMS_ENVIRONMENT="staging", HIMS_ACCEPT_LOCAL_DOCUMENT_STORAGE=True)
def test_throwaway_runs_can_accept_local_storage_explicitly():
    """Only CI smoke tests and short demos set this; real hospitals never do (ADR-020)."""
    from apps.staff.checks import document_storage_is_durable

    assert document_storage_is_durable(None) == []
