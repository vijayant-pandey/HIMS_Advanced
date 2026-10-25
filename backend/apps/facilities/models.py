from django.core.exceptions import ValidationError
from django.db import models

from apps.organizations.models import Country
from common.models import OrganizationOwnedModel, VersionedModel
from common.validators import validate_timezone


class Facility(OrganizationOwnedModel, VersionedModel):
    """A branch/site of the hospital organization (spec 4.1, 7.1).

    The physical hierarchy below it (building, floor, ward, room, bed) is delivered with the
    inpatient domain (HIMS-FAC-004).
    """

    class FacilityType(models.TextChoices):
        HOSPITAL = "hospital", "Hospital"
        CLINIC = "clinic", "Clinic"
        DIAGNOSTIC_CENTER = "diagnostic_center", "Diagnostic center"
        DAY_CARE = "day_care", "Day-care center"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    code = models.SlugField(max_length=32)
    name = models.CharField(max_length=255)
    facility_type = models.CharField(max_length=32, choices=FacilityType.choices)
    country = models.CharField(max_length=2, choices=Country.choices)
    state_region = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    postal_code = models.CharField(max_length=20)
    timezone = models.CharField(max_length=64, validators=[validate_timezone])
    phone = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        db_table = "facilities"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="facilities_code_unique")
        ]

    def __str__(self) -> str:
        return self.name


class Department(OrganizationOwnedModel, VersionedModel):
    class DepartmentType(models.TextChoices):
        CLINICAL = "clinical", "Clinical"
        DIAGNOSTIC = "diagnostic", "Diagnostic"
        PHARMACY = "pharmacy", "Pharmacy"
        SUPPORT = "support", "Support"
        ADMINISTRATIVE = "administrative", "Administrative"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name="departments")
    code = models.SlugField(max_length=32)
    name = models.CharField(max_length=255)
    department_type = models.CharField(max_length=32, choices=DepartmentType.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        db_table = "departments"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["facility", "code"], name="departments_code_unique")
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.facility.code})" if self.facility_id else self.name

    def clean(self):
        super().clean()
        adding_to_inactive = (
            self._state.adding
            and self.facility_id
            and self.facility.status != Facility.Status.ACTIVE
        )
        if adding_to_inactive:
            raise ValidationError(
                {"facility": "Departments can only be added to an active facility."}
            )
