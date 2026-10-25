"""Abstract base models shared by every domain (spec 28.2)."""

import uuid

from django.db import models


class UUIDPrimaryKeyModel(models.Model):
    """Immutable UUID identity. Business identifiers (MRN, invoice number...) are separate."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class VersionedModel(models.Model):
    """Optimistic-concurrency version; see common.concurrency (spec 29.3)."""

    version = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True


class OrganizationOwnedModel(UUIDPrimaryKeyModel, TimeStampedModel):
    """A record owned by the deployment's hospital organization.

    Each deployment holds exactly one organization (ADR-003). The foreign key is
    defence-in-depth and keeps rows self-describing in exports and restores; it is not the
    isolation mechanism (ADR-009).
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        abstract = True
