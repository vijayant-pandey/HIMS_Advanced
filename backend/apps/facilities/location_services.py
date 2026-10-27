"""Create and change locations: building, floor, ward, room and bed (HIMS-FAC-004).

All writes validate the model rules (LocationNode.clean), are audited with before/after values in
the same transaction, and use optimistic concurrency (``version``) for edits.
"""

from django.db import models, transaction

from apps.audit.services import AuditAction, model_changes, record_audit_event, snapshot
from common.concurrency import bump_version, lock_for_update

# Fields that may be edited after creation. Parents and codes never change (see design doc).
UPDATABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "building": ("name", "is_active"),
    "floor": ("name", "level", "is_active"),
    "ward": ("name", "ward_type", "department", "gender_restriction", "age_group", "is_active"),
    "room": ("name", "room_type", "is_isolation_capable", "is_active"),
    "bed": ("bed_type", "is_active"),
}


@transaction.atomic
def create_location(model: type[models.Model], *, actor, request=None, **data):
    instance = model(**data)
    instance.derive_from_parent()  # organization/facility come from the parent, before validation
    instance.full_clean()
    instance.save()
    record_audit_event(
        action=AuditAction.LOCATION_CREATED,
        resource_type=model._meta.model_name,
        resource_id=instance.pk,
        facility_id=instance.facility_id,
        actor=actor,
        request=request,
        changes={"after": snapshot(instance)},
    )
    return instance


@transaction.atomic
def update_location(model: type[models.Model], *, actor, pk, version: int, request=None, **changes):
    name = model._meta.model_name
    allowed = UPDATABLE_FIELDS[name]
    instance = lock_for_update(model, pk=pk, expected_version=version)
    before = snapshot(instance, allowed)
    for field, value in changes.items():
        if field not in allowed:
            raise ValueError(f"{field} is not updatable on {name}")
        setattr(instance, field, value)
    instance.full_clean()
    bump_version(instance)
    instance.save()
    record_audit_event(
        action=AuditAction.LOCATION_UPDATED,
        resource_type=name,
        resource_id=instance.pk,
        facility_id=instance.facility_id,
        actor=actor,
        request=request,
        changes=model_changes(before, snapshot(instance, allowed)),
    )
    return instance
