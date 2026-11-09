"""Hospital-editable message wording (HIMS-NOTIF-003). Standard wording: message_catalog.py.

A message always goes out: if a stored wording no longer fits the catalog (say a variable was
renamed in an upgrade), the standard wording is used and a warning is logged.
"""

import logging
import re

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.services import AuditAction, model_changes, record_audit_event, snapshot
from common.concurrency import bump_version, lock_for_update

from .message_catalog import BY_KEY, MESSAGES, MessageSpec
from .models import MessageTemplate

logger = logging.getLogger(__name__)

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_EXTRA_BLANK_LINES = re.compile(r"\n{3,}")
WORDING_FIELDS = ("subject", "body")


def ensure_templates() -> None:
    """A row for every message in the catalog, so both screens list them all. Blank wording
    means "use the standard". Never changes an existing row. Safe to run repeatedly."""
    existing = set(MessageTemplate.objects.values_list("key", flat=True))
    missing = [spec.code for spec in MESSAGES if spec.code not in existing]
    if missing:
        MessageTemplate.objects.bulk_create(
            [MessageTemplate(key=key) for key in missing], ignore_conflicts=True
        )


def check_wording(spec: MessageSpec, subject: str, body: str) -> dict[str, str]:
    """What is wrong with this wording, by field, in plain language. Empty when it is fine."""
    errors: dict[str, str] = {}
    known = {variable.name for variable in spec.variables}
    used: set[str] = set()
    for field, text in (("subject", subject), ("body", body)):
        names = _PLACEHOLDER.findall(text)
        used.update(names)
        unknown = sorted(set(names) - known)
        if unknown:
            errors[field] = f"{{{{{unknown[0]}}}}} is not available in this message."
        elif "{{" in _PLACEHOLDER.sub("", text) or "}}" in _PLACEHOLDER.sub("", text):
            errors[field] = "Write each placeholder like {{name}}, with two braces on each side."
    if not subject.strip():
        errors.setdefault("subject", "The subject cannot be empty.")
    elif "\n" in subject or "\r" in subject:
        errors.setdefault("subject", "The subject must be one line.")
    if not body.strip():
        errors.setdefault("body", "The message cannot be empty.")
    missing = sorted(spec.required - used)
    if missing:
        errors.setdefault(
            "body", f"This message must keep {{{{{missing[0]}}}}}: it is useless without it."
        )
    return errors


def fill(text: str, values: dict) -> str:
    """Put the values in. One pass only: a value that looks like a placeholder stays as text."""
    return _PLACEHOLDER.sub(lambda match: str(values.get(match.group(1), "")), text)


def _hospital_name() -> str:
    from apps.organizations.models import Organization

    organization = Organization.objects.only("display_name").first()
    return organization.display_name if organization else "HIMS"


def _wording(spec: MessageSpec) -> tuple[str, str]:
    row = MessageTemplate.objects.filter(key=spec.code).first()
    if row is None or not (row.subject or row.body):
        return spec.subject, spec.body
    subject, body = row.subject or spec.subject, row.body or spec.body
    if check_wording(spec, subject, body):
        logger.warning("message_template_invalid", extra={"template": spec.code})
        return spec.subject, spec.body
    return subject, body


def _render(subject: str, body: str, values: dict) -> tuple[str, str]:
    subject = " ".join(fill(subject, values).split())
    # An optional value left empty (a note, the deadlines) does not leave a gap behind.
    return subject, _EXTRA_BLANK_LINES.sub("\n\n", fill(body, values))


def render(key: str, values: dict) -> tuple[str, str]:
    """The subject and body to send for this message, in the hospital's wording."""
    spec = BY_KEY[key]
    return _render(*_wording(spec), {"hospital": _hospital_name(), **values})


def preview(spec: MessageSpec, subject: str, body: str) -> tuple[str, str]:
    """Wording not saved yet, filled with made-up sample values. Refused like a save if wrong."""
    errors = check_wording(spec, subject, body)
    if errors:
        raise ValidationError(errors)
    samples = {variable.name: variable.sample for variable in spec.variables}
    return _render(subject, body, {**samples, "hospital": _hospital_name()})


def to_store(spec: MessageSpec, subject: str, body: str) -> tuple[str, str]:
    """Wording the same as the standard is stored as "use the standard", so it follows upgrades.
    Spaces around the text do not count: forms trim them."""
    return (
        "" if subject.strip() == spec.subject.strip() else subject,
        "" if body.strip() == spec.body.strip() else body,
    )


def _audit(action, template, *, actor, request, before) -> None:
    record_audit_event(
        action=action,
        resource_type="message_template",
        resource_id=template.pk,
        actor=actor,
        request=request,
        metadata={"key": template.key},
        changes=model_changes(before, snapshot(template, WORDING_FIELDS)),
    )


@transaction.atomic
def update_template(
    *, actor, template_id, version: int, subject: str, body: str, request=None
) -> MessageTemplate:
    template = lock_for_update(MessageTemplate, pk=template_id, expected_version=version)
    spec = BY_KEY[template.key]
    errors = check_wording(spec, subject, body)
    if errors:
        raise ValidationError(errors)
    before = snapshot(template, WORDING_FIELDS)
    template.subject, template.body = to_store(spec, subject, body)
    template.updated_by = actor
    bump_version(template)
    template.save()
    _audit(
        AuditAction.MESSAGE_TEMPLATE_UPDATED, template, actor=actor, request=request, before=before
    )
    return template


@transaction.atomic
def reset_template(*, actor, template_id, version: int, request=None) -> MessageTemplate:
    template = lock_for_update(MessageTemplate, pk=template_id, expected_version=version)
    before = snapshot(template, WORDING_FIELDS)
    template.subject = ""
    template.body = ""
    template.updated_by = actor
    bump_version(template)
    template.save()
    _audit(
        AuditAction.MESSAGE_TEMPLATE_RESET, template, actor=actor, request=request, before=before
    )
    return template
