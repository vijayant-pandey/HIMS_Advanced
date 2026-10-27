"""Physical locations inside a facility: building, floor, ward/unit, room (HIMS-FAC-004).

Design: docs/architecture/data-architecture/locations-and-beds.md. Beds live in apps.beds.
Imported by apps/facilities/models.py so Django registers these models with this app.
"""

from django.core.exceptions import ValidationError
from django.db import models

from common.models import OrganizationOwnedModel, VersionedModel

from .models import Department, Facility


class LocationNode(OrganizationOwnedModel, VersionedModel):
    """Common rules for building / floor / ward / room (and beds in apps.beds).

    * ``organization`` and ``facility`` are derived from the parent on save, never user input.
    * The parent cannot change after creation (deactivate and recreate instead).
    * Children can only be added under an active parent; a parent with active children cannot
      be deactivated.
    * Codes are checked for uniqueness here as well as in the database, so admin forms show a
      clear message instead of a database error.
    """

    PARENT_FIELD: str = ""
    UNIQUE_WITHIN: str = ""  # field the code is unique within, e.g. "facility"
    CHILDREN: str = ""  # related name of children that must be inactive before deactivating

    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True

    @property
    def parent(self):
        return getattr(self, self.PARENT_FIELD)

    def derive_from_parent(self) -> None:
        parent = self.parent
        self.organization_id = parent.organization_id
        if self.PARENT_FIELD != "facility":
            self.facility_id = parent.facility_id

    def _parent_is_active(self) -> bool:
        parent = self.parent
        if isinstance(parent, Facility):
            return parent.status == Facility.Status.ACTIVE
        return parent.is_active

    def clean(self):
        super().clean()
        if not getattr(self, f"{self.PARENT_FIELD}_id", None):
            return
        self.derive_from_parent()
        errors: dict[str, str] = {}
        model = type(self)
        if self._state.adding:
            if not self._parent_is_active():
                errors[self.PARENT_FIELD] = "Items can only be added under an active parent."
        else:
            original_parent = (
                model.objects.filter(pk=self.pk)
                .values_list(f"{self.PARENT_FIELD}_id", flat=True)
                .first()
            )
            if original_parent is not None and original_parent != getattr(
                self, f"{self.PARENT_FIELD}_id"
            ):
                errors[self.PARENT_FIELD] = (
                    "This cannot be moved. Deactivate it and create a new one instead."
                )
        code = getattr(self, "code", None)
        if code and self.UNIQUE_WITHIN:
            scope = {f"{self.UNIQUE_WITHIN}_id": getattr(self, f"{self.UNIQUE_WITHIN}_id")}
            if model.objects.filter(code=code, **scope).exclude(pk=self.pk).exists():
                errors["code"] = f"This code is already used in this {self.UNIQUE_WITHIN}."
        has_active_children = (
            not self.is_active
            and self.CHILDREN
            and not self._state.adding
            and getattr(self, self.CHILDREN).filter(is_active=True).exists()
        )
        if has_active_children:
            errors["is_active"] = "Deactivate everything inside it first."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.derive_from_parent()
        super().save(*args, **kwargs)


class Building(LocationNode):
    PARENT_FIELD = "facility"
    UNIQUE_WITHIN = "facility"
    CHILDREN = "floors"

    facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name="buildings")
    code = models.SlugField(max_length=32)
    name = models.CharField(max_length=255)

    class Meta:
        db_table = "buildings"
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["facility", "code"], name="buildings_code_unique")
        ]

    def __str__(self) -> str:
        return self.name


class Floor(LocationNode):
    PARENT_FIELD = "building"
    CHILDREN = "wards"

    building = models.ForeignKey(Building, on_delete=models.PROTECT, related_name="floors")
    facility = models.ForeignKey(
        Facility, on_delete=models.PROTECT, related_name="+", editable=False
    )
    level = models.SmallIntegerField(help_text="-5 (basement) … 0 (ground) … 200")
    name = models.CharField(max_length=100)

    class Meta:
        db_table = "floors"
        ordering = ["level"]
        constraints = [
            models.UniqueConstraint(fields=["building", "level"], name="floors_level_unique"),
            models.CheckConstraint(
                condition=models.Q(level__gte=-5) & models.Q(level__lte=200),
                name="floors_level_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.building.name}, {self.name}" if self.building_id else self.name

    def clean(self):
        super().clean()
        if self.building_id and self.level is not None:
            clash = Floor.objects.filter(building_id=self.building_id, level=self.level)
            if clash.exclude(pk=self.pk).exists():
                raise ValidationError({"level": "This building already has that floor level."})


class Ward(LocationNode):
    """A ward or unit (general ward, ICU, NICU, operating theatre, …)."""

    PARENT_FIELD = "floor"
    UNIQUE_WITHIN = "facility"
    CHILDREN = "rooms"

    class WardType(models.TextChoices):
        GENERAL = "general", "General ward"
        PRIVATE = "private", "Private ward"
        ICU = "icu", "Intensive care unit (ICU)"
        HDU = "hdu", "High dependency unit (HDU)"
        NICU = "nicu", "Neonatal ICU (NICU)"
        PICU = "picu", "Pediatric ICU (PICU)"
        EMERGENCY = "emergency", "Emergency / casualty"
        MATERNITY = "maternity", "Maternity / labour"
        ISOLATION = "isolation", "Isolation ward"
        DAY_CARE = "day_care", "Day care"
        OPERATING_THEATRE = "operating_theatre", "Operating theatre complex"
        RECOVERY = "recovery", "Recovery / PACU"

    class GenderRestriction(models.TextChoices):
        ANY = "any", "Any"
        MALE = "male", "Male only"
        FEMALE = "female", "Female only"

    class AgeGroup(models.TextChoices):
        ANY = "any", "Any age"
        ADULT = "adult", "Adults"
        PEDIATRIC = "pediatric", "Children"
        NEONATAL = "neonatal", "Newborns"

    floor = models.ForeignKey(Floor, on_delete=models.PROTECT, related_name="wards")
    facility = models.ForeignKey(
        Facility, on_delete=models.PROTECT, related_name="wards", editable=False
    )
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, null=True, blank=True, related_name="wards"
    )
    code = models.SlugField(max_length=32)
    name = models.CharField(max_length=255)
    ward_type = models.CharField(max_length=32, choices=WardType.choices)
    gender_restriction = models.CharField(
        max_length=8, choices=GenderRestriction.choices, default=GenderRestriction.ANY
    )
    age_group = models.CharField(max_length=12, choices=AgeGroup.choices, default=AgeGroup.ANY)

    class Meta:
        db_table = "wards"
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["facility", "code"], name="wards_code_unique")
        ]
        indexes = [models.Index(fields=["facility", "ward_type"], name="wards_type_idx")]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        super().clean()
        if self.department_id and self.floor_id and self.department.facility_id != self.facility_id:
            raise ValidationError(
                {"department": "The department must belong to the same facility."}
            )


class Room(LocationNode):
    PARENT_FIELD = "ward"
    UNIQUE_WITHIN = "ward"
    CHILDREN = "beds"

    class RoomType(models.TextChoices):
        GENERAL = "general", "General room"
        PRIVATE = "private", "Private room"
        SEMI_PRIVATE = "semi_private", "Semi-private room"
        ICU_BAY = "icu_bay", "ICU bay"
        ISOLATION = "isolation", "Isolation room"
        OPERATING_ROOM = "operating_room", "Operating room"
        PROCEDURE = "procedure", "Procedure room"
        RECOVERY = "recovery", "Recovery bay"
        CONSULTATION = "consultation", "Consultation room"

    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name="rooms")
    facility = models.ForeignKey(
        Facility, on_delete=models.PROTECT, related_name="+", editable=False
    )
    code = models.SlugField(max_length=32)
    name = models.CharField(max_length=255)
    room_type = models.CharField(max_length=32, choices=RoomType.choices)
    is_isolation_capable = models.BooleanField(
        default=False, help_text="e.g. negative-pressure room for infection control"
    )

    class Meta:
        db_table = "rooms"
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["ward", "code"], name="rooms_code_unique")]

    def __str__(self) -> str:
        return f"{self.ward.name} / {self.name}" if self.ward_id else self.name
