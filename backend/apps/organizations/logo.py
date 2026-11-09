"""The hospital's logo file (HIMS-ORG-006; spec 4.1, 13.3).

PNG or JPEG only, read from the first bytes of the file, never trusted from its name or the
browser. SVG is refused on purpose: an SVG file can carry scripts. Stored under a random name, and
served only to people who are signed in.
"""

import uuid

from django.core.exceptions import ValidationError

LOGO_MAX_BYTES = 2 * 1024 * 1024
_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)


def logo_path(instance, filename: str) -> str:
    return f"organization-logo/{uuid.uuid4().hex}"


def logo_type(file) -> str | None:
    """The real type of the file, from its first bytes."""
    file.seek(0)
    head = file.read(16)
    file.seek(0)
    for signature, content_type in _SIGNATURES:
        if head.startswith(signature):
            return content_type
    return None


def validate_logo(file) -> None:
    if getattr(file, "_committed", False):
        return  # already stored and checked; saving other fields does not read it again
    if file.size == 0:
        raise ValidationError("The file is empty.")
    if file.size > LOGO_MAX_BYTES:
        raise ValidationError(
            f"The logo is too large; the limit is {LOGO_MAX_BYTES // (1024 * 1024)} MB."
        )
    if logo_type(file) is None:
        raise ValidationError("The logo must be a PNG or JPG picture.")
