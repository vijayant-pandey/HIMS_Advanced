"""Licence and qualification documents (HIMS-STAFF-005). See ADR-020."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditAction, record_audit_event
from common.exceptions import ConflictError

from .models import StaffCredential, StaffDocument, StaffMember, StaffQualification
from .uploads import safe_original_name, sha256_of, validate_upload


@transaction.atomic
def upload_document(
    *,
    actor,
    staff: StaffMember,
    upload,
    credential: StaffCredential | None = None,
    qualification: StaffQualification | None = None,
    request=None,
) -> StaffDocument:
    try:
        content_type, _extension = validate_upload(upload)
    except ValidationError as exc:
        raise ValidationError({"file": exc.messages}) from exc
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
