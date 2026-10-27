"""Bed operations (HIMS-FAC-004): bulk creation and the bed status state machine.

State machine (docs/architecture/data-architecture/locations-and-beds.md §3):
* Staff with ``beds.status.manage`` may move a bed between available, maintenance, blocked and
  out_of_service. A reason is required for anything other than available.
* reserved, occupied and cleaning belong to the admission/transfer/discharge and housekeeping
  workflows (Phase 3); they can be neither set nor left through this operation.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services import AuditAction, record_audit_event
from apps.facilities.location_services import create_location
from apps.facilities.models import Room
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError, DomainError
from common.outbox.services import publish_event

from .models import Bed

MAX_BULK_BEDS = 60


class BedStatusManagedByAdt(ConflictError):
    code = "BED_STATUS_MANAGED_BY_ADT"
    title = "Bed status is managed by admissions"


class StatusReasonRequired(DomainError):
    code = "STATUS_REASON_REQUIRED"
    title = "Reason required"


@transaction.atomic
def change_bed_status(
    *, actor, bed_id, version: int, status: str, reason: str = "", request=None
) -> Bed:
    bed = lock_for_update(Bed, pk=bed_id, expected_version=version)
    if bed.status in Bed.ADT_STATES:
        raise BedStatusManagedByAdt(
            f"This bed is {bed.get_status_display().lower()}. Its status changes through the "
            "admission, transfer, discharge and cleaning workflows."
        )
    if status not in Bed.OPERATIONAL_STATES:
        raise BedStatusManagedByAdt(
            "Reserved, occupied and cleaning are set by the admission and housekeeping workflows."
        )
    reason = (reason or "").strip()
    if status != Bed.Status.AVAILABLE and not reason:
        raise StatusReasonRequired("Say why the bed is unavailable (e.g. 'Broken side rail').")
    if not bed.is_active and status != Bed.Status.OUT_OF_SERVICE:
        raise ConflictError("Reactivate the bed before making it available.", code="BED_INACTIVE")
    if bed.status == status and bed.status_reason == reason:
        return bed  # nothing to change

    previous = bed.status
    bed.status = status
    bed.status_reason = "" if status == Bed.Status.AVAILABLE else reason
    bed.status_changed_at = timezone.now()
    bump_version(bed)
    bed.save(
        update_fields=["status", "status_reason", "status_changed_at", "version", "updated_at"]
    )
    record_audit_event(
        action=AuditAction.BED_STATUS_CHANGED,
        resource_type="bed",
        resource_id=bed.pk,
        facility_id=bed.facility_id,
        actor=actor,
        request=request,
        reason=reason,
        changes={"before": {"status": previous}, "after": {"status": status}},
    )
    # For the live bed board and housekeeping notifications (Phase 3). IDs only, no PHI.
    publish_event(
        event_type="bed.status.changed",
        aggregate_type="bed",
        aggregate_id=bed.pk,
        facility_id=bed.facility_id,
        payload={
            "bed_id": str(bed.pk),
            "ward_id": str(bed.ward_id),
            "from": previous,
            "to": status,
        },
    )
    return bed


@transaction.atomic
def create_beds_in_room(
    *, actor, room: Room, prefix: str, start: int, count: int, bed_type: str, request=None
) -> list[Bed]:
    """Add numbered beds to a room in one go, e.g. prefix 'B', start 1, count 4 -> B01..B04."""
    if not 1 <= count <= MAX_BULK_BEDS:
        raise DomainError(f"Add between 1 and {MAX_BULK_BEDS} beds at a time.", code="BULK_LIMIT")
    width = max(2, len(str(start + count - 1)))
    codes = [f"{prefix}{number:0{width}d}".lower() for number in range(start, start + count)]
    taken = set(
        Bed.objects.filter(ward_id=room.ward_id, code__in=codes).values_list("code", flat=True)
    )
    if taken:
        raise ConflictError(
            f"These bed codes already exist in this ward: {', '.join(sorted(taken))}.",
            code="DUPLICATE_CODE",
        )
    try:
        return [
            create_location(
                Bed, actor=actor, request=request, room=room, code=code, bed_type=bed_type
            )
            for code in codes
        ]
    except IntegrityError as exc:  # concurrent creation of the same codes
        raise ConflictError("Some of these beds were just created by someone else.") from exc
