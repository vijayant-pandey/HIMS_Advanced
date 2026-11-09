"""Equipment register rules (HIMS-FAC-009). The app and the admin console both come through here,
so they apply the same rules and write the same audit records."""

from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import AuditAction, model_changes, record_audit_event, snapshot
from apps.organizations.dates import hospital_today
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError

from .models import Equipment, EquipmentServiceRecord

DUE_SOON_DAYS = 30
OVERDUE = "overdue"
DUE_SOON = "due_soon"

UPDATABLE_FIELDS = (
    "department",
    "ward",
    "room",
    "location_note",
    "name",
    "category",
    "manufacturer",
    "model_name",
    "serial_number",
    "purchased_on",
    "warranty_until",
    "last_service_on",
    "next_service_due",
    "last_calibrated_on",
    "next_calibration_due",
    "notes",
)
Kind = EquipmentServiceRecord.Kind


def due_state(item: Equipment, today: date | None = None) -> str:
    """ "overdue", "due_soon" or "": the earlier of the service and calibration dates. Retired
    equipment is never due."""
    if item.status == Equipment.Status.RETIRED:
        return ""
    dates = [d for d in (item.next_service_due, item.next_calibration_due) if d]
    if not dates:
        return ""
    today = today or hospital_today()
    soonest = min(dates)
    if soonest < today:
        return OVERDUE
    return DUE_SOON if soonest <= today + timedelta(days=DUE_SOON_DAYS) else ""


def filter_due(queryset, state: str, today: date | None = None):
    """The same answer as ``due_state``, as a database filter (for lists)."""
    today = today or hospital_today()
    queryset = queryset.exclude(status=Equipment.Status.RETIRED)
    late = Q(next_service_due__lt=today) | Q(next_calibration_due__lt=today)
    if state == OVERDUE:
        return queryset.filter(late)
    soon = today + timedelta(days=DUE_SOON_DAYS)
    return queryset.filter(
        Q(next_service_due__range=(today, soon)) | Q(next_calibration_due__range=(today, soon))
    ).exclude(late)


def _audit(action, item, *, actor, request, **extra) -> None:
    record_audit_event(
        action=action,
        resource_type="equipment",
        resource_id=item.pk,
        facility_id=item.facility_id,
        actor=actor,
        request=request,
        **extra,
    )


@transaction.atomic
def create_equipment(*, actor, organization, facility, asset_tag, request=None, **fields):
    item = Equipment(
        organization=organization,
        facility=facility,
        asset_tag=asset_tag.strip().upper(),
        **fields,
    )
    item.full_clean()
    item.save()
    _audit(
        AuditAction.EQUIPMENT_CREATED,
        item,
        actor=actor,
        request=request,
        changes={"after": snapshot(item)},
    )
    return item


@transaction.atomic
def update_equipment(*, actor, equipment_id, version: int, request=None, **changes) -> Equipment:
    item = lock_for_update(Equipment, pk=equipment_id, expected_version=version)
    before = snapshot(item, UPDATABLE_FIELDS)
    for field, value in changes.items():
        if field not in UPDATABLE_FIELDS:
            raise ValueError(f"{field} is not updatable")
        setattr(item, field, value)
    item.full_clean()
    bump_version(item)
    item.save()
    _audit(
        AuditAction.EQUIPMENT_UPDATED,
        item,
        actor=actor,
        request=request,
        changes=model_changes(before, snapshot(item, UPDATABLE_FIELDS)),
    )
    return item


@transaction.atomic
def change_status(
    *, actor, equipment_id, version: int, status: str, reason: str = "", request=None
) -> Equipment:
    item = lock_for_update(Equipment, pk=equipment_id, expected_version=version)
    reason = (reason or "").strip()
    if status != Equipment.Status.IN_SERVICE and not reason:
        raise ValidationError({"reason": "Say why this equipment cannot be used."})
    new_reason = "" if status == Equipment.Status.IN_SERVICE else reason
    if item.status == status and item.status_reason == new_reason:
        return item  # nothing to change
    previous = item.status
    item.status = status
    item.status_reason = new_reason
    item.status_changed_at = timezone.now()
    bump_version(item)
    item.save(
        update_fields=["status", "status_reason", "status_changed_at", "version", "updated_at"]
    )
    _audit(
        AuditAction.EQUIPMENT_STATUS_CHANGED,
        item,
        actor=actor,
        request=request,
        reason=reason,
        changes={"before": {"status": previous}, "after": {"status": status}},
    )
    return item


def _apply_dates(item: Equipment, record: EquipmentServiceRecord) -> None:
    """The newest visit sets the register's dates. A visit entered late, older than the last
    one, joins the history without moving them."""
    last, next_due = (
        ("last_calibrated_on", "next_calibration_due")
        if record.kind == Kind.CALIBRATION
        else ("last_service_on", "next_service_due")
    )
    current = getattr(item, last)
    if current is not None and record.performed_on < current:
        return
    setattr(item, last, record.performed_on)
    setattr(item, next_due, record.next_due)


@transaction.atomic
def record_service(*, actor, record: EquipmentServiceRecord, request=None):
    """Add ``record`` (not saved yet) to its equipment's history and update the register's
    dates. Adding a fact needs no version: nothing the person was looking at is overwritten."""
    item = Equipment.objects.select_for_update().get(pk=record.equipment_id)
    if item.status == Equipment.Status.RETIRED:
        raise ConflictError(
            "This equipment is retired. Bring it back into use before recording a visit.",
            code="EQUIPMENT_RETIRED",
        )
    errors = {}
    if record.performed_on > hospital_today():
        errors["performed_on"] = "This date is in the future."
    if record.next_due and record.next_due <= record.performed_on:
        errors["next_due"] = "The next visit must be after this one."
    if errors:
        raise ValidationError(errors)
    record.facility_id = item.facility_id
    record.recorded_by = actor
    record.full_clean()
    record.save()
    _apply_dates(item, record)
    bump_version(item)
    item.save()
    _audit(
        AuditAction.EQUIPMENT_SERVICE_RECORDED,
        item,
        actor=actor,
        request=request,
        metadata={
            "record_id": str(record.pk),
            "kind": record.kind,
            "performed_on": record.performed_on.isoformat(),
            "next_due": record.next_due.isoformat() if record.next_due else None,
        },
    )
    return record
