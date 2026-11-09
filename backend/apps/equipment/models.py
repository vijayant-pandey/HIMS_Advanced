"""Equipment register (HIMS-FAC-009; spec 4.12 "equipment inventory, maintenance and calibration",
4.2 department equipment): what the hospital owns, where it is, whether it can be used and when
it is due for service. Requests, job orders and transport wait for the product owner's decision.

How it works: docs/workflows/equipment-register.md. Service and calibration visits are kept in
EquipmentServiceRecord, which the database refuses to change or delete.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from apps.facilities.models import Department, Facility, Room, Ward
from common.models import OrganizationOwnedModel, UUIDPrimaryKeyModel, VersionedModel


class Equipment(OrganizationOwnedModel, VersionedModel):
    class Category(models.TextChoices):
        MONITORING = "monitoring", "Patient monitoring"
        LIFE_SUPPORT = "life_support", "Life support (ventilator, defibrillator)"
        INFUSION = "infusion", "Infusion and syringe pumps"
        OXYGEN = "oxygen", "Oxygen and gases"
        IMAGING = "imaging", "Imaging"
        LABORATORY = "laboratory", "Laboratory"
        SURGICAL = "surgical", "Operating theatre and surgical"
        STERILIZATION = "sterilization", "Sterilization"
        MOBILITY = "mobility", "Wheelchairs and stretchers"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        IN_SERVICE = "in_service", "In service"
        MAINTENANCE = "maintenance", "Under maintenance"
        OUT_OF_SERVICE = "out_of_service", "Out of service"
        RETIRED = "retired", "Retired"

    facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name="equipment")
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.PROTECT, related_name="equipment"
    )
    ward = models.ForeignKey(
        Ward, null=True, blank=True, on_delete=models.PROTECT, related_name="equipment"
    )
    room = models.ForeignKey(
        Room, null=True, blank=True, on_delete=models.PROTECT, related_name="equipment"
    )
    location_note = models.CharField(
        max_length=120, blank=True, help_text="Anything more about where it is, e.g. 'Store 2'."
    )
    asset_tag = models.CharField(
        max_length=40,
        validators=[
            RegexValidator(
                r"^[A-Za-z0-9][A-Za-z0-9._/-]*$",
                "Use letters, numbers and . _ / - only, e.g. ICU-VENT-01.",
            )
        ],
        help_text="The hospital's own number on the label. Set once; it cannot change later.",
    )
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    manufacturer = models.CharField(max_length=120, blank=True)
    model_name = models.CharField(max_length=120, blank=True)
    serial_number = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_SERVICE)
    status_reason = models.CharField(max_length=255, blank=True)
    status_changed_at = models.DateTimeField(default=timezone.now)
    purchased_on = models.DateField(null=True, blank=True)
    warranty_until = models.DateField(null=True, blank=True)
    last_service_on = models.DateField(null=True, blank=True)
    next_service_due = models.DateField(null=True, blank=True)
    last_calibrated_on = models.DateField(null=True, blank=True)
    next_calibration_due = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, max_length=1000, help_text="No patient details.")

    class Meta:
        db_table = "equipment"
        verbose_name_plural = "equipment"
        constraints = [
            models.UniqueConstraint(fields=["facility", "asset_tag"], name="equipment_tag_unique")
        ]
        indexes = [
            models.Index(fields=["facility", "status"], name="equipment_status_idx"),
            models.Index(fields=["next_service_due"], name="equipment_service_due_idx"),
            models.Index(fields=["next_calibration_due"], name="equipment_calibration_due_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.asset_tag} {self.name}"

    def clean(self) -> None:
        super().clean()
        errors = {}
        if self.room_id and not self.ward_id:
            self.ward_id = self.room.ward_id
        if self.department_id and self.department.facility_id != self.facility_id:
            errors["department"] = "This department belongs to another facility."
        if self.ward_id and self.ward.facility_id != self.facility_id:
            errors["ward"] = "This ward belongs to another facility."
        if self.room_id and self.room.ward_id != self.ward_id:
            errors["room"] = "This room is in another ward."
        if self.status != self.Status.IN_SERVICE and not self.status_reason.strip():
            errors["status_reason"] = "Say why this equipment cannot be used."
        if errors:
            raise ValidationError(errors)


class EquipmentServiceRecord(UUIDPrimaryKeyModel):
    """One service, repair or calibration visit. Append-only (database trigger): a mistake is
    corrected by adding another record, so the history can be trusted in an inspection."""

    class Kind(models.TextChoices):
        SERVICE = "service", "Service"
        REPAIR = "repair", "Repair"
        CALIBRATION = "calibration", "Calibration"

    equipment = models.ForeignKey(
        Equipment, on_delete=models.PROTECT, related_name="service_records"
    )
    facility = models.ForeignKey(
        Facility, on_delete=models.PROTECT, related_name="+", editable=False
    )
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.SERVICE)
    performed_on = models.DateField()
    performed_by = models.CharField(
        max_length=120, blank=True, help_text="Who did it: the technician or company."
    )
    notes = models.CharField(max_length=500, blank=True, help_text="No patient details.")
    next_due = models.DateField(
        null=True, blank=True, help_text="When the next one is due, if it is known."
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        editable=False,
    )
    recorded_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "equipment_service_records"
        ordering = ["-performed_on", "-recorded_at"]
        indexes = [
            models.Index(fields=["equipment", "-performed_on"], name="equipment_records_item_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} on {self.performed_on}"
