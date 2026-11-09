"""Beds (HIMS-FAC-004). Bed allocation to admissions arrives in Phase 3 in this same app.

Design: docs/architecture/data-architecture/locations-and-beds.md (tables, indexes and the bed
status state machine). Every status change is kept in BedStatusChange (HIMS-FAC-008), shown on
the bed board; the audit log keeps it too.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.facilities.location_models import LocationNode
from apps.facilities.models import Facility, Room, Ward
from common.models import UUIDPrimaryKeyModel

_UNKNOWN = object()


class Bed(LocationNode):
    PARENT_FIELD = "room"
    UNIQUE_WITHIN = "ward"

    class BedType(models.TextChoices):
        GENERAL = "general", "General"
        SEMI_PRIVATE = "semi_private", "Semi-private"
        PRIVATE = "private", "Private"
        DELUXE = "deluxe", "Deluxe / suite"
        ICU = "icu", "ICU"
        HDU = "hdu", "HDU"
        NICU = "nicu", "NICU (cot / incubator)"
        PICU = "picu", "PICU"
        ISOLATION = "isolation", "Isolation"
        DAY_CARE = "day_care", "Day care"
        LABOUR = "labour", "Labour / delivery"
        RECOVERY = "recovery", "Recovery"
        EMERGENCY_TROLLEY = "emergency_trolley", "Emergency trolley"

    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        RESERVED = "reserved", "Reserved"
        OCCUPIED = "occupied", "Occupied"
        CLEANING = "cleaning", "Cleaning"
        MAINTENANCE = "maintenance", "Maintenance"
        BLOCKED = "blocked", "Blocked"
        OUT_OF_SERVICE = "out_of_service", "Out of service"

    # States owned by the admission/transfer/discharge and housekeeping workflows (Phase 3).
    ADT_STATES = frozenset({Status.RESERVED, Status.OCCUPIED, Status.CLEANING})
    # States staff may set directly in this release (beds.status.manage).
    OPERATIONAL_STATES = frozenset(
        {Status.AVAILABLE, Status.MAINTENANCE, Status.BLOCKED, Status.OUT_OF_SERVICE}
    )

    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="beds")
    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name="beds", editable=False)
    facility = models.ForeignKey(
        Facility, on_delete=models.PROTECT, related_name="beds", editable=False
    )
    code = models.SlugField(max_length=32, help_text="Bed label, unique within the ward")
    bed_type = models.CharField(max_length=32, choices=BedType.choices)
    # Status is never edited as a field (spec 26.3): only apps.beds.services.change_bed_status.
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.AVAILABLE, editable=False
    )
    status_reason = models.CharField(max_length=255, blank=True, editable=False)
    status_changed_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "beds"
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["ward", "code"], name="beds_code_unique"),
            models.CheckConstraint(
                condition=Q(is_active=True) | Q(status="out_of_service"),
                name="beds_inactive_out_of_service",
            ),
        ]
        indexes = [
            models.Index(fields=["facility", "ward", "status"], name="beds_board_idx"),
            models.Index(fields=["facility", "bed_type", "status"], name="beds_type_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.ward.code}/{self.code}" if self.ward_id else self.code

    def derive_from_parent(self) -> None:
        super().derive_from_parent()
        self.ward_id = self.room.ward_id

    @classmethod
    def from_db(cls, db, field_names, values):
        bed = super().from_db(db, field_names, values)
        # A field that was not loaded is missing here: then nothing is compared on save.
        bed._saved_status = bed.__dict__.get("status", _UNKNOWN)
        return bed

    def save(self, *args, **kwargs):
        """Keeps one history row per status change, whoever made it: the status service, or
        switching the bed off (app or console). Callers attach ``_hims_actor`` (who) and may
        attach ``_status_note`` (the reason, when it is not kept on the bed itself)."""
        previous = getattr(self, "_saved_status", _UNKNOWN)
        super().save(*args, **kwargs)
        if previous is not _UNKNOWN and previous != self.status:
            BedStatusChange.objects.create(
                bed=self,
                facility_id=self.facility_id,
                ward_id=self.ward_id,
                from_status=previous,
                to_status=self.status,
                reason=getattr(self, "_status_note", self.status_reason)[:255],
                changed_by=getattr(self, "_hims_actor", None),
                changed_at=self.status_changed_at,
            )
        self._saved_status = self.status

    def clean(self):
        super().clean()
        if not self.is_active and self.status != self.Status.OUT_OF_SERVICE:
            current = Bed.objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if current in self.ADT_STATES:
                raise ValidationError(
                    {
                        "is_active": "A bed that is reserved, occupied or being cleaned "
                        "cannot be deactivated."
                    }
                )
            self.status = self.Status.OUT_OF_SERVICE
            self.status_reason = "Deactivated"
            self.status_changed_at = timezone.now()


class BedStatusChange(UUIDPrimaryKeyModel):
    """One change of a bed's status: from, to, why, who and when (spec 4.10; HIMS-FAC-008).

    Append-only: a database trigger refuses changes and deletes, like the audit log. The bed
    board shows a bed's recent changes from here, so ward staff can see why a bed is blocked
    without reading the audit log (which only auditors may).
    """

    bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name="status_changes")
    facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name="+")
    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name="+")
    from_status = models.CharField(max_length=16, choices=Bed.Status.choices)
    to_status = models.CharField(max_length=16, choices=Bed.Status.choices)
    reason = models.CharField(max_length=255, blank=True, help_text="No patient details.")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "bed_status_changes"
        ordering = ["-changed_at"]
        indexes = [
            models.Index(fields=["bed", "-changed_at"], name="bed_changes_bed_idx"),
            models.Index(fields=["facility", "-changed_at"], name="bed_changes_facility_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.bed}: {self.from_status} -> {self.to_status}"
