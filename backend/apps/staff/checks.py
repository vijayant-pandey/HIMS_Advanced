"""Deploy checks for document storage (ADR-020)."""

from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def document_storage_is_durable(app_configs, **kwargs):
    """Hosted environments must not keep staff documents on the server's own disk, which on
    container hosts (e.g. Render) is wiped on every deploy."""
    from django.core.files.storage import FileSystemStorage, default_storage

    hosted = settings.HIMS_ENVIRONMENT in ("qa", "staging", "production")
    if hosted and isinstance(default_storage, FileSystemStorage):
        return [
            Warning(
                "Staff documents are stored on local disk.",
                hint="Configure S3-compatible storage before relying on uploads (ADR-020).",
                id="hims.W001",
            )
        ]
    return []
