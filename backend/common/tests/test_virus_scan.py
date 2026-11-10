"""Virus scanning of uploads (HIMS-SEC-013; spec 4.22, 13.3). The scanner is a fake ClamAV
service on this computer, or the built-in test-file check. The test file is the standard,
harmless anti-virus test file. All data is synthetic."""

import io
import socket
import threading
from datetime import date

import pytest
from django.core import mail
from django.core.checks import run_checks
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.organizations.models import Organization
from apps.staff.models import ScanStatus, StaffCredential, StaffDocument, StaffMember
from common import virus_scan
from common.admin.tests.test_console_additions import console

API = "/api/v1"
PDF = b"%PDF-1.4\n% synthetic test document\n%%EOF\n"


class FakeClamd:
    """Speaks just enough of ClamAV's protocol: PING, and INSTREAM answered with ``reply``."""

    def __init__(self, reply=b"stream: OK\0"):
        self.reply = reply
        self.received = b""
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen()
        self.port = self.server.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while True:
            try:
                connection, _ = self.server.accept()
            except OSError:
                return
            with connection:
                command = b""
                while not command.endswith(b"\0"):
                    part = connection.recv(1)
                    if not part:
                        break
                    command += part
                if command == b"zPING\0":
                    connection.sendall(b"PONG\0")
                    continue
                data = b""
                while True:
                    size = int.from_bytes(self._exactly(connection, 4), "big")
                    if size == 0:
                        break
                    data += self._exactly(connection, size)
                self.received = data
                connection.sendall(self.reply)

    @staticmethod
    def _exactly(connection, count):
        data = b""
        while len(data) < count:
            part = connection.recv(count - len(data))
            if not part:
                break
            data += part
        return data

    def close(self):
        self.server.close()

    def settings(self):
        return override_settings(
            HIMS_VIRUS_SCANNER="clamd",
            HIMS_CLAMD_HOST="127.0.0.1",
            HIMS_CLAMD_PORT=self.port,
            HIMS_CLAMD_TIMEOUT=5,
        )


@pytest.fixture
def clamd():
    servers = []

    def start(reply=b"stream: OK\0"):
        server = FakeClamd(reply)
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.close()


def _closed_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


@pytest.fixture
def nurse(organization, make_user):
    return StaffMember.objects.create(
        organization=organization,
        user=make_user(email="nurse.scan@synthetic.test"),
        employee_number="EMP-SCAN-1",
        given_name="Mary",
        family_name="Scan",
        staff_type="nurse",
        joined_on="2026-01-05",
    )


@pytest.fixture
def licence(nurse):
    return StaffCredential.objects.create(
        organization_id=nurse.organization_id,
        staff=nurse,
        credential_type="nursing_registration",
        registration_number="KNC-SCAN-1",
        issuing_authority="Karnataka Nursing Council",
        jurisdiction="IN-KA",
        expires_at=date(2027, 1, 1),
    )


def _upload(client, staff, licence, content=PDF, name="licence.pdf"):
    return client.post(
        f"{API}/staff/{staff.pk}/documents/",
        {"file": SimpleUploadedFile(name, content), "credential": str(licence.pk)},
        format="multipart",
    )


# --- The scanners ------------------------------------------------------------------------------


def test_the_test_file_check_finds_only_the_test_file():
    scanner = virus_scan.TestFileScanner()
    found = scanner.scan(io.BytesIO(virus_scan.test_file()))
    assert (found.status, found.threat) == (virus_scan.INFECTED, "EICAR test file")
    assert scanner.scan(io.BytesIO(PDF)).status == virus_scan.NOT_SCANNED  # not "clean": no promise
    assert scanner.protects is False


def test_no_scanner_checks_nothing():
    assert virus_scan.NoScanner().scan(io.BytesIO(virus_scan.test_file())).status == "not_scanned"


def test_clamd_clean_and_the_whole_file_is_sent(clamd):
    server = clamd()
    big = PDF + b"x" * 200_000  # several chunks
    with server.settings():
        result = virus_scan.scanner().scan(io.BytesIO(big))
        assert virus_scan.scanner().ping() is True
    assert (result.status, result.scanner) == (virus_scan.CLEAN, "clamd")
    assert server.received == big


def test_clamd_names_what_it_found(clamd):
    server = clamd(b"stream: Win.Test.EICAR_HDB-1 FOUND\0")
    with server.settings():
        result = virus_scan.scanner().scan(io.BytesIO(PDF))
    assert (result.status, result.threat) == (virus_scan.INFECTED, "Win.Test.EICAR_HDB-1")


def test_clamd_unreachable_or_failing_refuses_rather_than_lets_through(clamd):
    with override_settings(HIMS_VIRUS_SCANNER="clamd", HIMS_CLAMD_PORT=_closed_port()):
        with pytest.raises(virus_scan.ScannerUnavailable):
            virus_scan.scanner().scan(io.BytesIO(PDF))
        assert virus_scan.scanner().ping() is False
    server = clamd(b"INSTREAM size limit exceeded. ERROR\0")
    with server.settings(), pytest.raises(virus_scan.ScannerUnavailable):
        virus_scan.scanner().scan(io.BytesIO(PDF))


@pytest.mark.parametrize(
    "environment,scanner,accepted,warned",
    [
        ("production", "test-file", False, True),
        ("staging", "none", False, True),
        ("production", "clamd", False, False),
        ("production", "test-file", True, False),
        ("local", "test-file", False, False),
    ],
)
def test_hosted_without_a_real_scanner_is_a_deploy_warning(environment, scanner, accepted, warned):
    with override_settings(
        HIMS_ENVIRONMENT=environment,
        HIMS_VIRUS_SCANNER=scanner,
        HIMS_ACCEPT_UNSCANNED_UPLOADS=accepted,
    ):
        ids = {message.id for message in run_checks(include_deployment_checks=True)}
    assert ("hims.W002" in ids) is warned


# --- Staff documents ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_virus_is_refused_audited_reported_and_never_stored(
    client_for, admin_user, nurse, licence, make_user, system_roles
):
    officer = make_user(
        email="security.officer@synthetic.test", role=system_roles["compliance-officer"]
    )
    mail.outbox.clear()
    response = _upload(client_for(admin_user), nurse, licence, virus_scan.test_file(), "cv.pdf")
    assert response.status_code == 400
    assert "virus" in str(response.json())
    assert not StaffDocument.objects.exists()
    event = AuditEvent.objects.get(action=AuditAction.UPLOAD_BLOCKED)
    assert event.outcome == "failure" and event.actor_id == admin_user.pk
    assert event.metadata["threat"] == "EICAR test file" and len(event.metadata["sha256"]) == 64
    assert "cv.pdf" not in str(event.metadata)  # a file name may name a person
    alert = next(m for m in mail.outbox if officer.email in m.to)
    assert "virus was blocked" in alert.subject and "cv.pdf" not in alert.body


@pytest.mark.django_db
def test_a_file_without_a_virus_is_stored_with_how_it_was_checked(
    client_for, admin_user, nurse, licence, clamd
):
    with override_settings(HIMS_VIRUS_SCANNER="test-file"):
        row = _upload(client_for(admin_user), nurse, licence).json()
    assert (row["scan_status"], row["scanned_by"]) == ("not_scanned", "test-file")
    server = clamd()
    with server.settings():
        row = _upload(client_for(admin_user), nurse, licence).json()
    assert (row["scan_status"], row["scanned_by"]) == ("clean", "clamd")
    upload_event = AuditEvent.objects.filter(action=AuditAction.STAFF_DOCUMENT_UPLOADED).latest(
        "occurred_at"
    )
    assert upload_event.metadata["scan"] == "clean"


@pytest.mark.django_db
def test_while_the_scanner_is_unreachable_uploads_are_paused(
    client_for, admin_user, nurse, licence
):
    with override_settings(HIMS_VIRUS_SCANNER="clamd", HIMS_CLAMD_PORT=_closed_port()):
        response = _upload(client_for(admin_user), nurse, licence)
    assert response.status_code == 503 and response.json()["code"] == "SCANNER_UNAVAILABLE"
    assert not StaffDocument.objects.exists()


@pytest.mark.django_db
def test_a_virus_found_later_blocks_the_file_and_archives_it(
    client_for, admin_user, nurse, licence, clamd
):
    client = client_for(admin_user)
    with override_settings(HIMS_VIRUS_SCANNER="none"):
        row = _upload(client, nurse, licence).json()
    assert client.get(f"{API}/staff-documents/{row['id']}/download/").status_code == 200
    server = clamd(b"stream: Pdf.Exploit.Test FOUND\0")
    mail.outbox.clear()
    with server.settings(), override_settings(HIMS_APP_BASE_URL="http://app.test"):
        call_command("scan_documents", stdout=io.StringIO())
    document = StaffDocument.objects.get(pk=row["id"])
    assert document.scan_status == ScanStatus.INFECTED
    assert document.scan_threat == "Pdf.Exploit.Test" and document.archived_at is not None
    blocked = client.get(f"{API}/staff-documents/{row['id']}/download/")
    assert blocked.status_code == 409 and blocked.json()["code"] == "DOCUMENT_INFECTED"
    assert AuditEvent.objects.filter(action=AuditAction.STAFF_DOCUMENT_VIRUS_FOUND).count() == 1
    summary = AuditEvent.objects.get(action=AuditAction.STAFF_DOCUMENTS_SCANNED)
    assert summary.metadata["infected"] == 1
    # Checked again later: nothing changes, and it is never unblocked by a later clean result.
    clean = clamd()
    with clean.settings():
        call_command("scan_documents", "--all", stdout=io.StringIO())
    assert StaffDocument.objects.get(pk=row["id"]).scan_status == ScanStatus.INFECTED


@pytest.mark.django_db
def test_checking_stored_files_with_only_the_test_check_promises_nothing(
    client_for, admin_user, nurse, licence
):
    with override_settings(HIMS_VIRUS_SCANNER="none"):
        _upload(client_for(admin_user), nurse, licence)
    out = io.StringIO()
    call_command("scan_documents", stdout=out)
    assert "1 that this scanner cannot really check" in out.getvalue()
    assert StaffDocument.objects.get().scan_status == ScanStatus.NOT_SCANNED


# --- Logo ----------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_logo_with_a_virus_is_refused(client_for, admin_user, organization):
    response = client_for(admin_user).post(
        f"{API}/organization/logo/",
        {"file": SimpleUploadedFile("logo.png", virus_scan.test_file())},
        format="multipart",
    )
    assert response.status_code == 400 and "virus" in str(response.json())
    assert not Organization.objects.get().logo
    assert AuditEvent.objects.get(action=AuditAction.UPLOAD_BLOCKED).metadata["where"] == (
        "uploaded as the hospital logo"
    )


# --- Status and console --------------------------------------------------------------------------


@pytest.mark.django_db
def test_status_for_the_compliance_page(client_for, admin_user, nurse, licence, clamd):
    client = client_for(admin_user)
    _upload(client, nurse, licence)
    _upload(client, nurse, licence, virus_scan.test_file())
    body = client.get(f"{API}/security/upload-scanning/").json()
    assert body["scanner"] == "test-file" and body["protects"] is False
    assert body["reachable"] is None
    assert body["documents"] == {"clean": 0, "not_scanned": 1, "infected": 0}
    assert body["blocked_last_30_days"] == 1
    assert body["traces"] == {
        "exporter": "none",
        "sent_elsewhere": False,
        "error_text_filtered": True,
    }
    server = clamd()
    with server.settings():
        assert client.get(f"{API}/security/upload-scanning/").json()["reachable"] is True
        scanned = client.post(f"{API}/security/upload-scanning/scan/").json()
    assert (scanned["checked"], scanned["clean"]) == (1, 1)


@pytest.mark.django_db
def test_status_needs_compliance_permission(client_for, make_user, system_roles, facility_a):
    hr = client_for(make_user(role=system_roles["hr-credentialing-officer"]))
    assert hr.get(f"{API}/security/upload-scanning/").status_code == 403
    officer = client_for(make_user(role=system_roles["compliance-officer"]))
    assert officer.get(f"{API}/security/upload-scanning/").status_code == 200
    auditor = client_for(make_user(role=system_roles["auditor"]))
    assert auditor.post(f"{API}/security/upload-scanning/scan/").status_code == 403


@pytest.mark.django_db
def test_console_refuses_a_virus_and_shows_the_status(admin_user, nurse, licence, organization):
    client = console(admin_user, confirmed=True)
    response = client.post(
        "/admin/staff/staffdocument/add/",
        {
            "staff": str(nurse.pk),
            "credential": str(licence.pk),
            "file": SimpleUploadedFile("cv.pdf", virus_scan.test_file()),
        },
    )
    assert response.status_code == 200 and "virus" in response.content.decode()
    assert not StaffDocument.objects.exists()
    assert AuditEvent.objects.get(action=AuditAction.UPLOAD_BLOCKED).actor_id == admin_user.pk
    stored = client.post(
        "/admin/staff/staffdocument/add/",
        {
            "staff": str(nurse.pk),
            "credential": str(licence.pk),
            "file": SimpleUploadedFile("licence.pdf", PDF),
        },
    )
    assert stored.status_code == 302
    assert StaffDocument.objects.get().scanned_by == "test-file"
    page = client.get("/admin/compliance/consoleaccessblock/security-status/").content.decode()
    assert "Virus scanning of uploads" in page and "Error text in traces" in page
    logo = client.post(
        f"/admin/organizations/organization/{organization.pk}/change/",
        {
            "legal_name": organization.legal_name,
            "display_name": organization.display_name,
            "default_timezone": organization.default_timezone,
            "leave_year_start_month": 1,
            "logo": SimpleUploadedFile("logo.png", virus_scan.test_file()),
        },
    )
    assert logo.status_code == 200 and "virus" in logo.content.decode()


@pytest.mark.django_db
def test_console_action_checks_selected_documents(admin_user, client_for, nurse, licence, clamd):
    with override_settings(HIMS_VIRUS_SCANNER="none"):
        row = _upload(client_for(admin_user), nurse, licence).json()
    server = clamd()
    client = console(admin_user, confirmed=True)
    with server.settings():
        client.post(
            "/admin/staff/staffdocument/",
            {"action": "scan_selected", "_selected_action": [row["id"]]},
        )
    assert StaffDocument.objects.get().scan_status == ScanStatus.CLEAN
