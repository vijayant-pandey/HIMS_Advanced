"""Job titles, specialties and qualification types: hospital-maintained catalogs (HIMS-STAFF-010).

HIMS ships standard entries (seeded once by migrations, never overwritten afterwards); each
hospital can rename them, switch them off, and add its own (``is_custom``). Codes never change
because records point to them. Nothing is deleted: a switched-off entry disappears from
drop-down lists but stays on existing records.
"""

import re

from django.db import transaction

from apps.audit.services import AuditAction, model_changes, record_audit_event, snapshot
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError

from .models import Designation, QualificationType, Specialty

CATALOGS = {
    "designation": (
        Designation,
        ("name", "category", "country", "seniority", "description", "is_active"),
    ),
    "specialty": (Specialty, ("name", "is_active")),
    "qualification_type": (QualificationType, ("name", "category", "country", "is_active")),
}


def suggest_code(name: str, country: str = "") -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50] or "item"
    return f"{country.lower()}-{base}" if country else base


@transaction.atomic
def create_catalog_item(kind: str, *, actor, request=None, **data):
    model, _fields = CATALOGS[kind]
    name_taken = model.objects.filter(
        name__iexact=data["name"].strip(),
        **({"country": data["country"]} if "country" in data else {}),
    ).exists()
    if name_taken:
        raise ConflictError("An entry with this name already exists.", code="DUPLICATE_NAME")
    if data.get("code"):
        if model.objects.filter(code=data["code"]).exists():
            raise ConflictError("An entry with this code already exists.", code="DUPLICATE_CODE")
    else:  # generated from the name; a number is added if another entry already uses it
        base = suggest_code(data["name"], data.get("country", ""))
        code, n = base, 2
        while model.objects.filter(code=code).exists():
            code, n = f"{base}-{n}", n + 1
        data["code"] = code
    item = model(is_custom=True, **{**data, "name": data["name"].strip()})
    item.full_clean()
    item.save()
    record_audit_event(
        action=AuditAction.CATALOG_ITEM_CREATED,
        resource_type=model._meta.model_name,
        resource_id=item.pk,
        actor=actor,
        request=request,
        changes={"after": snapshot(item)},
    )
    return item


@transaction.atomic
def update_catalog_item(kind: str, *, actor, item_id, version: int, request=None, **changes):
    model, allowed = CATALOGS[kind]
    item = lock_for_update(model, pk=item_id, expected_version=version)
    before = snapshot(item, allowed)
    for field, value in changes.items():
        if field not in allowed:
            raise ValueError(f"{field} is not updatable on {kind}")
        setattr(item, field, value.strip() if isinstance(value, str) else value)
    item.full_clean()
    bump_version(item)
    item.save()
    record_audit_event(
        action=AuditAction.CATALOG_ITEM_UPDATED,
        resource_type=model._meta.model_name,
        resource_id=item.pk,
        actor=actor,
        request=request,
        changes=model_changes(before, snapshot(item, allowed)),
    )
    return item
