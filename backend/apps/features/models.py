"""A hospital's feature choices (HIMS-ORG-004). The features themselves live in catalog.py."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from common.models import OrganizationOwnedModel, VersionedModel

from . import catalog


class FeatureFlag(OrganizationOwnedModel, VersionedModel):
    """One setting: hospital-wide (``facility`` empty) or for one facility.

    ``enabled`` is True (on), False (off) or None (use the default). Rows are never deleted;
    going back to the default keeps the row, and the audit log keeps every change.
    """

    key = models.CharField(max_length=100)
    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="feature_flags",
        help_text="Leave empty for the whole hospital.",
    )
    enabled = models.BooleanField(
        null=True, blank=True, help_text="Empty = use the default for this hospital's country."
    )
    reason = models.CharField(
        max_length=255, help_text="Why it was changed (kept in the audit log)."
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "feature_flags"
        ordering = ["key", "facility__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["key", "facility"],
                nulls_distinct=False,
                name="feature_flag_unique",
                violation_error_message="This feature already has a setting for this scope.",
            )
        ]

    def __str__(self) -> str:
        scope = self.facility.code.upper() if self.facility_id else "hospital-wide"
        return f"{self.feature.name if self.feature else self.key} ({scope})"

    @property
    def feature(self) -> catalog.Feature | None:
        return catalog.BY_KEY.get(self.key)

    def _fill_organization(self) -> None:
        if not self.organization_id:
            from apps.organizations.selectors import get_deployment_organization

            self.organization_id = get_deployment_organization().pk

    def clean_fields(self, exclude=None):
        self._fill_organization()  # always this deployment's hospital, never client input
        super().clean_fields(exclude)

    def clean(self):
        super().clean()
        self._fill_organization()
        feature = self.feature
        if feature is None:
            raise ValidationError({"key": "Unknown feature."})
        errors = {}
        if self.facility_id and feature.scope != catalog.FACILITY:
            errors["facility"] = "This feature is set for the whole hospital only."
        if self.enabled:
            from apps.organizations.models import Organization

            country = (
                Organization.objects.filter(pk=self.organization_id)
                .values_list("country", flat=True)
                .first()
            )
            if not feature.available:
                errors["enabled"] = (
                    f"Not available yet ({feature.planned_phase}). "
                    "It can be switched on once built."
                )
            elif feature.countries and country not in feature.countries:
                errors["enabled"] = "This feature is not offered in this hospital's country."
        if not (self.reason or "").strip():
            errors["reason"] = "Say why, e.g. 'Approved by the medical director on 28 Oct'."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self._fill_organization()
        super().save(*args, **kwargs)
