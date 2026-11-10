"""Checks for uploaded staff documents (HIMS-STAFF-005, spec 4.22, 13.3).

The real type is read from the first bytes of the file, never trusted from its name or the
browser. Only PDF, JPEG and PNG are accepted. Every file is also checked for viruses
(``check_upload``, HIMS-SEC-013) before it is stored.
"""

import hashlib
import uuid
from pathlib import PurePath

from django.conf import settings
from django.core.exceptions import ValidationError

# Signature -> (content type, file extension)
_SIGNATURES = (
    (b"%PDF-", ("application/pdf", "pdf")),
    (b"\xff\xd8\xff", ("image/jpeg", "jpg")),
    (b"\x89PNG\r\n\x1a\n", ("image/png", "png")),
)

ALLOWED_DESCRIPTION = "PDF, JPG or PNG"


def detect_type(upload) -> tuple[str, str] | None:
    upload.seek(0)
    head = upload.read(16)
    upload.seek(0)
    for signature, kind in _SIGNATURES:
        if head.startswith(signature):
            return kind
    return None


def validate_upload(upload) -> tuple[str, str]:
    """Return (content_type, extension) or raise a plain-language ValidationError."""
    limit = settings.HIMS_UPLOAD_MAX_BYTES
    if upload.size == 0:
        raise ValidationError("The file is empty.")
    if upload.size > limit:
        raise ValidationError(f"The file is too large; the limit is {limit // (1024 * 1024)} MB.")
    kind = detect_type(upload)
    if kind is None:
        raise ValidationError(f"Only {ALLOWED_DESCRIPTION} files can be uploaded.")
    return kind


def check_upload(upload, *, actor=None, request=None):
    """Size, then viruses, then type, for a new staff document. Returns
    (content_type, extension, scan result). Call outside a transaction: a refusal is audited."""
    from common.virus_scan import check_upload as scan_upload

    limit = settings.HIMS_UPLOAD_MAX_BYTES
    if 0 < upload.size <= limit:  # the size messages come from validate_upload below
        result = scan_upload(
            upload, where="uploaded as a staff document", actor=actor, request=request
        )
    else:
        result = None
    content_type, extension = validate_upload(upload)
    return content_type, extension, result


def sha256_of(upload) -> str:
    digest = hashlib.sha256()
    upload.seek(0)
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    return digest.hexdigest()


def stored_name(instance, filename: str) -> str:
    """Random file name inside a per-person folder: the original name (which may contain a
    patient or staff name) never becomes part of a path."""
    extension = PurePath(filename).suffix.lower().lstrip(".") or "bin"
    return f"staff-documents/{instance.staff_id}/{uuid.uuid4().hex}.{extension}"


def safe_original_name(filename: str) -> str:
    """Keep the name people recognise, without any folder parts or control characters."""
    name = PurePath(filename.replace("\\", "/")).name
    cleaned = "".join(ch for ch in name if ch.isprintable() and ch not in '"<>|')
    return (cleaned or "document")[:200]
