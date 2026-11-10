"""Virus scanning of uploaded files (HIMS-SEC-013; spec 4.22, 13.3). How to use it:
docs/workflows/virus-scanning.md.

Every uploaded file is checked before it is stored. ``HIMS_VIRUS_SCANNER`` chooses the scanner:

* ``clamd``     ClamAV's scanning service, reached over the network (``HIMS_CLAMD_HOST`` and
  ``HIMS_CLAMD_PORT``). Real protection, and required when hosted (deploy check ``hims.W002``).
* ``test-file`` (default) recognises only the standard anti-virus test file, so the refusal can
  be tried on a developer PC. It is not protection: files are recorded as "not checked".
* ``none``      nothing is checked.

If ClamAV cannot be reached, uploads are refused until it is back (fail closed): a file that could
not be checked is never stored as if it had been.

A refused file is never written anywhere. The refusal is logged and audited with the file's
fingerprint (never its name or contents), and the compliance team is emailed.
"""

import logging
import socket
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError

from common.exceptions import DomainError

logger = logging.getLogger(__name__)

CLEAN = "clean"
INFECTED = "infected"
NOT_SCANNED = "not_scanned"
SCANNERS = ("clamd", "test-file", "none")
_CHUNK = 64 * 1024
# The standard anti-virus test file (EICAR), built from pieces so that this source file is not
# itself mistaken for a virus by the scanner on a developer's PC.
_TEST_FILE = b"".join(
    (
        b"X5O!P%@AP[4",
        bytes([92]),
        b"PZX54(P^)7CC)7}$",
        b"EICAR-STANDARD-",
        b"ANTIVIRUS-TEST-FILE!$H+H*",
    )
)


@dataclass(frozen=True)
class ScanResult:
    status: str
    scanner: str
    threat: str = ""


class ScannerUnavailable(DomainError):
    status_code = 503
    code = "SCANNER_UNAVAILABLE"
    title = "Virus scanning unavailable"


def test_file() -> bytes:
    """The standard anti-virus test file, for tests and the manual check. It is harmless."""
    return _TEST_FILE


def _chunks(file):
    file.seek(0)
    while True:
        chunk = file.read(_CHUNK)
        if not chunk:
            break
        yield chunk
    file.seek(0)


class NoScanner:
    name = "none"
    label = "No virus scanning"
    protects = False

    def scan(self, file) -> ScanResult:
        return ScanResult(NOT_SCANNED, self.name)

    def ping(self) -> bool:
        return True


class TestFileScanner(NoScanner):
    """Recognises only the standard test file, at the start of the file as the standard says."""

    name = "test-file"
    label = "Test file only (not real protection)"

    def scan(self, file) -> ScanResult:
        file.seek(0)
        head = file.read(len(_TEST_FILE))
        file.seek(0)
        if head == _TEST_FILE:
            return ScanResult(INFECTED, self.name, "EICAR test file")
        return ScanResult(NOT_SCANNED, self.name)


class ClamdScanner:
    """ClamAV's daemon, spoken to with its INSTREAM command (no extra library needed)."""

    name = "clamd"
    label = "ClamAV"
    protects = True

    def __init__(self, host: str, port: int, timeout: float):
        self.address = (host, port)
        self.timeout = timeout

    def _ask(self, send) -> str:
        try:
            with socket.create_connection(self.address, timeout=self.timeout) as connection:
                send(connection)
                reply = b""
                while not reply.endswith(b"\0"):
                    part = connection.recv(4096)
                    if not part:
                        break
                    reply += part
        except OSError as exc:
            logger.warning("virus_scanner_unreachable", extra={"error_type": type(exc).__name__})
            raise ScannerUnavailable(
                "Files cannot be checked for viruses right now, so uploads are paused. "
                "Try again in a few minutes; if it continues, tell your administrator."
            ) from None
        return reply.rstrip(b"\0").decode("utf-8", "replace").strip()

    def scan(self, file) -> ScanResult:
        def send(connection):
            connection.sendall(b"zINSTREAM\0")
            for chunk in _chunks(file):
                connection.sendall(len(chunk).to_bytes(4, "big") + chunk)
            connection.sendall(b"\0\0\0\0")

        reply = self._ask(send)
        if reply.endswith("FOUND"):
            threat = reply.removeprefix("stream:").removesuffix("FOUND").strip()
            return ScanResult(INFECTED, self.name, threat[:120] or "unknown")
        if reply.endswith("OK"):
            return ScanResult(CLEAN, self.name)
        logger.warning("virus_scanner_error", extra={"reply": reply[:200]})
        raise ScannerUnavailable(
            "The virus scanner could not check this file. Try again; if it continues, tell your "
            "administrator."
        )

    def ping(self) -> bool:
        try:
            return self._ask(lambda connection: connection.sendall(b"zPING\0")) == "PONG"
        except ScannerUnavailable:
            return False


def scanner():
    choice = settings.HIMS_VIRUS_SCANNER
    if choice == "clamd":
        return ClamdScanner(
            settings.HIMS_CLAMD_HOST, settings.HIMS_CLAMD_PORT, settings.HIMS_CLAMD_TIMEOUT
        )
    return TestFileScanner() if choice == "test-file" else NoScanner()


def _report_blocked(file, result: ScanResult, *, where: str, actor, request) -> None:
    from apps.audit.models import AuditEvent
    from apps.audit.services import AuditAction, record_audit_event
    from apps.staff.uploads import sha256_of

    fingerprint = sha256_of(file)
    logger.warning(
        "upload_blocked_virus",
        extra={"where": where, "threat": result.threat, "sha256": fingerprint},
    )
    record_audit_event(
        action=AuditAction.UPLOAD_BLOCKED,
        resource_type="upload",
        resource_id=fingerprint[:64],
        actor=actor,
        request=request,
        outcome=AuditEvent.Outcome.FAILURE,
        reason=f"Virus found: {result.threat}",
        metadata={
            "where": where,
            "threat": result.threat,
            "scanner": result.scanner,
            "size_bytes": getattr(file, "size", None),
            "sha256": fingerprint,
        },
    )
    alert_compliance_team(where=where, threat=result.threat)


def alert_compliance_team(*, where: str, threat: str) -> None:
    """No file name and no person in the email: the details are behind the sign-in."""
    from django.utils import timezone

    from apps.compliance.incidents import compliance_team_emails
    from apps.notifications.services import send_message
    from apps.organizations.dates import hospital_time

    send_message(
        "security.upload_blocked",
        to=compliance_team_emails(),
        values={
            "where": where,
            "threat": threat,
            "when": f"{hospital_time(timezone.now()):%d %b %Y %H:%M %Z}",
            "link": f"{settings.HIMS_APP_BASE_URL.rstrip('/')}/audit",
        },
    )


def check_upload(file, *, where: str, actor=None, request=None) -> ScanResult:
    """Scan ``file`` before it is stored. A virus raises ValidationError, after the refusal is
    logged, audited and reported, so call this outside any transaction that the error would roll
    back. A scanner that cannot be reached raises ScannerUnavailable."""
    result = scanner().scan(file)
    if result.status == INFECTED:
        _report_blocked(file, result, where=where, actor=actor, request=request)
        raise ValidationError(
            f"This file contains a virus or harmful content ({result.threat}), so it was not "
            "saved. Do not open it on your computer; tell your IT team."
        )
    return result


def status() -> dict:
    """What protects uploads now, for the Compliance page and the console."""
    current = scanner()
    reachable = current.ping() if current.protects else None
    return {
        "scanner": current.name,
        "label": current.label,
        "protects": current.protects,
        "reachable": reachable,
    }
