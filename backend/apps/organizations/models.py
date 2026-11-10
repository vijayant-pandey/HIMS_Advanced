from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from common.models import TimeStampedModel, UUIDPrimaryKeyModel, VersionedModel
from common.validators import validate_timezone

from .logo import logo_path, validate_logo


class Country(models.TextChoices):
    UNITED_STATES = "US", "United States"
    INDIA = "IN", "India"


class Currency(models.TextChoices):
    USD = "USD", "US Dollar"
    INR = "INR", "Indian Rupee"


class Organization(UUIDPrimaryKeyModel, TimeStampedModel, VersionedModel):
    """The hospital organization served by this dedicated deployment (ADR-003, ADR-009).

    Created only by provisioning (``provision_organization``), never through the public API.
    The ``singleton`` constraint guarantees one organization per deployment database.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    deployment_id = models.SlugField(max_length=64, unique=True)
    legal_name = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    country = models.CharField(max_length=2, choices=Country.choices)
    default_timezone = models.CharField(max_length=64, validators=[validate_timezone])
    default_currency = models.CharField(max_length=3, choices=Currency.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    singleton = models.BooleanField(default=True, editable=False)
    leave_year_start_month = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="The month the leave year starts: 1 is January, 4 is April (HIMS-STAFF-013).",
    )
    # Letterhead on printouts and emails (HIMS-ORG-006; spec 4.1). All optional.
    logo = models.FileField(
        upload_to=logo_path,
        max_length=120,
        blank=True,
        validators=[validate_logo],
        help_text="PNG or JPG, up to 2 MB.",
    )
    letterhead_address = models.TextField(blank=True, max_length=500)
    letterhead_phone = models.CharField(max_length=40, blank=True)
    letterhead_email = models.EmailField(blank=True)
    letterhead_website = models.CharField(max_length=200, blank=True)
    letterhead_registration = models.CharField(
        max_length=120,
        blank=True,
        help_text="The registration or tax number to show, e.g. 'Reg. no. MH-1234'.",
    )
    letterhead_footer = models.CharField(
        max_length=255, blank=True, help_text="A line at the very end, e.g. a helpline."
    )

    class Meta:
        db_table = "organizations"
        constraints = [
            models.UniqueConstraint(fields=["singleton"], name="organizations_one_per_deployment"),
            models.CheckConstraint(
                condition=Q(singleton=True), name="organizations_singleton_true"
            ),
        ]

    def __str__(self) -> str:
        return self.display_name

    def letterhead_lines(self) -> list[str]:
        """The letterhead's details, in print order, leaving out what is not filled in."""
        contact = " · ".join(
            part
            for part in (self.letterhead_phone, self.letterhead_email, self.letterhead_website)
            if part
        )
        lines = [*self.letterhead_address.splitlines(), contact, self.letterhead_registration]
        return [line.strip() for line in [*lines, self.letterhead_footer] if line.strip()]
