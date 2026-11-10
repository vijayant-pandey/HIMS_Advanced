"""Deploy checks for document storage (ADR-020)."""

from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def document_storage_is_durable(app_configs, **kwargs):
    """Hosted environments must not keep staff documents on the server's own disk, which on
    container hosts (e.g. Render) is wiped on every deploy."""
    from django.core.files.storage import FileSystemStorage, default_storage

    hosted = settings.HIMS_ENVIRONMENT in ("qa", "staging", "production")
    accepted = settings.HIMS_ACCEPT_LOCAL_DOCUMENT_STORAGE  # throw-away runs only (e.g. CI)
    if hosted and not accepted and isinstance(default_storage, FileSystemStorage):
        return [
            Warning(
                "Staff documents are stored on local disk.",
                hint="Configure S3-compatible storage before relying on uploads (ADR-020).",
                id="hims.W001",
            )
        ]
    return []


@register(Tags.security, deploy=True)
def uploads_are_scanned(app_configs, **kwargs):
    """Hosted environments check every upload with a real virus scanner (HIMS-SEC-013)."""
    hosted = settings.HIMS_ENVIRONMENT in ("qa", "staging", "production")
    accepted = settings.HIMS_ACCEPT_UNSCANNED_UPLOADS  # throw-away runs only (e.g. CI)
    if hosted and not accepted and settings.HIMS_VIRUS_SCANNER != "clamd":
        return [
            Warning(
                "Uploaded files are not checked for viruses.",
                hint="Set HIMS_VIRUS_SCANNER=clamd with HIMS_CLAMD_HOST and HIMS_CLAMD_PORT "
                "(docs/workflows/virus-scanning.md).",
                id="hims.W002",
            )
        ]
    return []
