"""Encryption key rotation for stored secrets (spec 13.3 "managed encryption keys and rotation";
HIMS-SEC-011 finding F-03).

``HIMS_FIELD_ENCRYPTION_KEYS`` lists keys newest first; any listed key can read a value. A new key
was usable at once, but nothing encrypted the stored values again, so an old key could never be
removed. ``rotate_encryption_keys`` (command) re-encrypts every stored secret with the newest key;
``status`` says how many values still need an older one (Compliance page, console).

How to rotate: put the new key first in the list and restart, run
``python manage.py rotate_encryption_keys``, check that nothing is left on older keys, then remove
the old key ([how-to](../../../docs/workflows/encryption-keys.md)).
"""

from django.db import transaction

from apps.audit.services import AuditAction, record_audit_event
from common import crypto

# Every column that holds a value from common.crypto.encrypt.
ENCRYPTED_FIELDS = (
    ("identity.MfaDevice", "secret_encrypted", "Authenticator app secrets"),
    ("notifications.Notification", "body_encrypted", "Messages not yet delivered"),
    ("patients.PatientIdentifier", "value_encrypted", "Patient ID numbers"),
    ("patients.IdentifierHashKey", "key_encrypted", "Key for ID-number fingerprints"),
)


def _model(label: str):
    from django.apps import apps

    return apps.get_model(label)


def _rows(label: str, field: str):
    return _model(label).objects.exclude(**{field: ""}).only("pk", field)


def status() -> dict:
    """How many stored secrets each column holds, and how many still need an older key."""
    fields = []
    for label, field, name in ENCRYPTED_FIELDS:
        values = list(_rows(label, field).values_list(field, flat=True))
        fields.append(
            {
                "name": name,
                "values": len(values),
                "on_older_keys": sum(1 for value in values if not crypto.is_on_newest_key(value)),
            }
        )
    return {
        "keys": crypto.key_count(),
        "fields": fields,
        "on_older_keys": sum(item["on_older_keys"] for item in fields),
    }


def rotate(*, dry_run: bool = False, actor=None) -> dict:
    """Encrypt every stored secret again with the newest key. Repeating it is harmless."""
    rotated = {}
    with transaction.atomic():
        for label, field, name in ENCRYPTED_FIELDS:
            count = 0
            for row in _rows(label, field).select_for_update():
                value = getattr(row, field)
                if crypto.is_on_newest_key(value):
                    continue
                count += 1
                if not dry_run:
                    # update(), not save(): no model rules or timestamps change for a re-encryption.
                    type(row).objects.filter(pk=row.pk).update(**{field: crypto.rotate(value)})
            rotated[name] = count
        if not dry_run:
            record_audit_event(
                action=AuditAction.DATABASE_ENCRYPTION_ROTATED,
                resource_type="encryption_keys",
                actor=actor,
                metadata={"keys": crypto.key_count(), "rotated": rotated},
            )
    return rotated
