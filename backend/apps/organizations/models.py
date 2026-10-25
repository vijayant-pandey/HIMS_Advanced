from django.db import models
from django.db.models import Q

from common.models import TimeStampedModel, UUIDPrimaryKeyModel, VersionedModel
from common.validators import validate_timezone


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
