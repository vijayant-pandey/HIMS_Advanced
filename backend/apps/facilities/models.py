from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

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

    def clean(self):
        super().clean()
        if _deactivating(self):
            from .closing import explain, facility_blockers

            blockers = facility_blockers(self)
            if blockers:
                raise ValidationError({"status": explain(blockers)})


def _deactivating(instance) -> bool:
    """True when an existing active record is being set to inactive."""
    if instance._state.adding or instance.status != "inactive":
        return False
    previous = type(instance).objects.filter(pk=instance.pk).values_list("status", flat=True)
    return previous.first() == "active"


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
    # HIMS-FAC-007 (spec 4.2): who leads it, and when it is open (weekly hours below).
    head = models.ForeignKey(
        "staff.StaffMember",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="departments_headed",
        help_text="Must be a working staff member currently posted in this department.",
    )
    open_24_hours = models.BooleanField(
        default=False, help_text="e.g. Emergency, ICU. Weekly hours are ignored when set."
    )

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
        if self.head_id and not self._state.adding:
            from .closing import head_problem

            problem = head_problem(self, self.head)
            if problem:
                raise ValidationError({"head": problem})
        reactivating_under_inactive = (
            not self._state.adding
            and self.status == self.Status.ACTIVE
            and self.facility_id
            and self.facility.status != Facility.Status.ACTIVE
        )
        if reactivating_under_inactive:
            raise ValidationError({"status": "Reactivate the facility first."})
        if _deactivating(self):
            from .closing import department_blockers, explain

            blockers = department_blockers(self)
            if blockers:
                raise ValidationError({"status": explain(blockers)})


class DepartmentService(OrganizationOwnedModel, VersionedModel):
    """A service the department offers, e.g. "Echocardiography" or "OPD consultation"
    (spec 4.2). Prices come with billing (Phase 5). Never deleted: switched off instead."""

    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="services")
    name = models.CharField(max_length=150)
    description = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "department_services"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "department",
                name="department_service_name_unique",
                violation_error_message="This department already has a service with that name.",
            )
        ]

    def __str__(self) -> str:
        return self.name


class DepartmentHours(models.Model):
    """One opening session on one weekday, in the facility's time zone (e.g. Mon 09:00-13:00).

    A day can have several sessions (morning and evening OPD); a day with none is closed.
    The whole week is replaced at once (apps.facilities.services.set_department_hours)."""

    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="hours")
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    opens_at = models.TimeField()
    closes_at = models.TimeField()

    class Meta:
        db_table = "department_hours"
        ordering = ["weekday", "opens_at"]
        verbose_name_plural = "department hours"
        constraints = [
            models.CheckConstraint(
                condition=Q(closes_at__gt=F("opens_at")),
                name="department_hours_closes_after_opens",
                violation_error_message="Closing time must be after opening time.",
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_weekday_display()} {self.opens_at:%H:%M}-{self.closes_at:%H:%M}"


# Physical locations (building, floor, ward, room) live in their own module.
from .location_models import Building, Floor, Room, Ward  # noqa: E402, F401
