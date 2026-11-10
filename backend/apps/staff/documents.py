"""Licence and qualification documents (HIMS-STAFF-005). See ADR-020."""

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditAction, record_audit_event
from common import virus_scan
from common.exceptions import ConflictError

from .models import ScanStatus, StaffCredential, StaffDocument, StaffMember, StaffQualification
from .uploads import check_upload, safe_original_name, sha256_of

logger = logging.getLogger(__name__)
SCAN_BATCH = 200


def upload_document(
    *,
    actor,
    staff: StaffMember,
    upload,
    credential: StaffCredential | None = None,
    qualification: StaffQualification | None = None,
    request=None,
) -> StaffDocument:
    """Checked first, outside the transaction, so that a refused virus stays in the audit log."""
    try:
        content_type, _extension, scan = check_upload(upload, actor=actor, request=request)
    except ValidationError as exc:
        raise ValidationError({"file": exc.messages}) from exc
    return _store_document(
        actor=actor,
        staff=staff,
        upload=upload,
        content_type=content_type,
        scan=scan,
        credential=credential,
        qualification=qualification,
        request=request,
    )


@transaction.atomic
def _store_document(
    *, actor, staff, upload, content_type, scan, credential, qualification, request
) -> StaffDocument:
    document = StaffDocument(
        organization_id=staff.organization_id,
        staff=staff,
        credential=credential,
        qualification=qualification,
        original_name=safe_original_name(upload.name),
        content_type=content_type,
        size_bytes=upload.size,
        sha256=sha256_of(upload),
        uploaded_by=actor,
        scan_status=scan.status,
        scanned_by=scan.scanner,
        scanned_at=timezone.now(),
    )
    document.file = upload
    document.full_clean(exclude=["file"])
    document.save()
    record_audit_event(
        action=AuditAction.STAFF_DOCUMENT_UPLOADED,
        resource_type="staff_document",
        resource_id=document.pk,
        actor=actor,
        request=request,
        metadata={
            "staff_member_id": str(staff.pk),
            "for": "credential" if credential else "qualification",
            "content_type": content_type,
            "size_bytes": document.size_bytes,
            "sha256": document.sha256,
            "scan": scan.status,
        },
    )
    return document


@transaction.atomic
def archive_document(*, actor, document_id, reason: str, request=None) -> StaffDocument:
    """A wrong or outdated file is archived, never deleted (kept for history and audits)."""
    document = StaffDocument.objects.select_for_update().get(pk=document_id)
    if document.archived_at is not None:
        raise ConflictError("This document is already archived.", code="ALREADY_ARCHIVED")
    document.archived_at = timezone.now()
    document.archived_by = actor
    document.archive_reason = reason.strip()
    document.save(update_fields=["archived_at", "archived_by", "archive_reason", "updated_at"])
    record_audit_event(
        action=AuditAction.STAFF_DOCUMENT_ARCHIVED,
        resource_type="staff_document",
        resource_id=document.pk,
        actor=actor,
        request=request,
        reason=document.archive_reason,
        metadata={"staff_member_id": str(document.staff_id)},
    )
    return document


def record_download(*, actor, document: StaffDocument, request=None) -> None:
    """Every view or download of a document is in the audit log (who, when, which file)."""
    record_audit_event(
        action=AuditAction.STAFF_DOCUMENT_DOWNLOADED,
        resource_type="staff_document",
        resource_id=document.pk,
        actor=actor,
        request=request,
        metadata={"staff_member_id": str(document.staff_id), "sha256": document.sha256},
    )


def ensure_openable(document: StaffDocument) -> None:
    if document.scan_status == ScanStatus.INFECTED:
        raise ConflictError(
            "A virus was found in this file, so it cannot be opened. It is kept only as a record.",
            code="DOCUMENT_INFECTED",
        )


def scan_stored_documents(
    *, actor=None, request=None, documents=None, only_unchecked: bool = True
) -> dict:
    """Check documents already stored (those from before scanning, or after the virus list was
    updated). A virus found blocks the file, archives the document and tells the compliance team.
    Stops at the first scanner failure. At most 200 at a time; run again for more."""
    scanner = virus_scan.scanner()
    rows = documents if documents is not None else StaffDocument.objects.all()
    rows = rows.exclude(scan_status=ScanStatus.INFECTED)
    if only_unchecked:
        rows = rows.filter(scan_status=ScanStatus.NOT_SCANNED)
    counts = {"checked": 0, "clean": 0, "infected": 0, "not_checked": 0, "missing": 0}
    for document in rows.order_by("created_at")[:SCAN_BATCH]:
        try:
            with document.file.open("rb") as stored:
                result = scanner.scan(stored)
        except (OSError, ValueError):
            counts["missing"] += 1
            continue
        counts["checked"] += 1
        if result.status == virus_scan.INFECTED:
            counts["infected"] += 1
            _block(document, result, actor=actor, request=request)
        elif result.status == virus_scan.CLEAN:
            counts["clean"] += 1
            StaffDocument.objects.filter(pk=document.pk).update(
                scan_status=ScanStatus.CLEAN, scanned_by=result.scanner, scanned_at=timezone.now()
            )
        else:
            counts["not_checked"] += 1
    record_audit_event(
        action=AuditAction.STAFF_DOCUMENTS_SCANNED,
        resource_type="staff_document",
        resource_id="",
        actor=actor,
        request=request,
        metadata={"scanner": scanner.name, **counts},
    )
    return counts


@transaction.atomic
def _block(document: StaffDocument, result, *, actor, request) -> None:
    document = StaffDocument.objects.select_for_update().get(pk=document.pk)
    document.scan_status = ScanStatus.INFECTED
    document.scanned_by = result.scanner
    document.scanned_at = timezone.now()
    document.scan_threat = result.threat
    if document.archived_at is None:
        document.archived_at = timezone.now()
        document.archived_by = actor
        document.archive_reason = "A virus was found by a later check"
    document.save()
    logger.warning(
        "stored_document_virus_found",
        extra={"document_id": str(document.pk), "threat": result.threat},
    )
    record_audit_event(
        action=AuditAction.STAFF_DOCUMENT_VIRUS_FOUND,
        resource_type="staff_document",
        resource_id=document.pk,
        actor=actor,
        request=request,
        reason=f"Virus found: {result.threat}",
        metadata={"staff_member_id": str(document.staff_id), "sha256": document.sha256},
    )
    transaction.on_commit(
        lambda: virus_scan.alert_compliance_team(
            where="stored as a staff document", threat=result.threat
        )
    )
