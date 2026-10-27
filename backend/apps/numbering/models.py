"""Hospital numbering schemes (HIMS-ORG-003, spec 4.1, 28.2).

Business numbers (MRN, encounter, invoice, claim) are separate from database keys (UUIDs).
Design: docs/architecture/data-architecture/numbering-schemes.md.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

from common.models import OrganizationOwnedModel, VersionedModel

from . import formatting

# GST rule (India): an invoice number may have at most 16 characters (letters, digits, - and /)
# and must be unique within the financial year. CGST Rules, rule 46(b).
INDIA_INVOICE_MAX_LENGTH = 16


class NumberingScheme(OrganizationOwnedModel, VersionedModel):
    """How one kind of number is built. One per document type, either for the whole hospital
    (``facility`` empty) or for one facility (overrides the hospital-wide scheme there)."""

    class DocumentType(models.TextChoices):
        MRN = "mrn", "Patient record number (MRN)"
        ENCOUNTER = "encounter", "Encounter / visit number"
        INVOICE = "invoice", "Invoice number"
        CLAIM = "claim", "Insurance claim number"

    class Period(models.TextChoices):
        NONE = formatting.NONE, "Never restarts"
        CALENDAR_YEAR = formatting.CALENDAR_YEAR, "Restarts every calendar year"
        FINANCIAL_YEAR = formatting.FINANCIAL_YEAR, "Restarts every financial year"
        MONTH = formatting.MONTH, "Restarts every month"

    class YearFormat(models.TextChoices):
        FULL = "full", "Full (2026, 2026-27)"
        SHORT = "short", "Short (26, 26-27)"

    class Separator(models.TextChoices):
        DASH = "-", "Dash (-)"
        SLASH = "/", "Slash (/)"
        NONE = "", "None"

    document_type = models.CharField(max_length=16, choices=DocumentType.choices)
    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="numbering_schemes",
        help_text="Leave empty for the whole hospital. Set to give one facility its own series.",
    )
    prefix = models.CharField(
        max_length=10,
        blank=True,
        validators=[RegexValidator(r"^[A-Z0-9]*$", "Use capital letters and digits only.")],
    )
    separator = models.CharField(
        max_length=1, choices=Separator.choices, default=Separator.DASH, blank=True
    )
    include_facility_code = models.BooleanField(
        default=False, help_text="Put the facility code in the number, e.g. ENC-BLR-2026-0001."
    )
    period = models.CharField(max_length=16, choices=Period.choices, default=Period.NONE)
    year_format = models.CharField(
        max_length=5, choices=YearFormat.choices, default=YearFormat.FULL
    )
    financial_year_start_month = models.PositiveSmallIntegerField(
        default=4, help_text="India: 4 (April). US: usually 1 (January) or the hospital's own."
    )
    padding = models.PositiveSmallIntegerField(
        default=6, help_text="Digits in the running number, e.g. 6 gives 000001."
    )
    start_at = models.PositiveIntegerField(
        default=1, help_text="First running number of each new series."
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "numbering_schemes"
        ordering = ["document_type", "facility__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["document_type", "facility"],
                nulls_distinct=False,
                name="numbering_scheme_unique",
                violation_error_message="This document type already has a scheme for this scope.",
            ),
            models.CheckConstraint(
                condition=Q(padding__gte=3) & Q(padding__lte=12), name="numbering_padding_range"
            ),
            models.CheckConstraint(
                condition=Q(financial_year_start_month__gte=1)
                & Q(financial_year_start_month__lte=12),
                name="numbering_fy_month_range",
            ),
            models.CheckConstraint(
                condition=~Q(document_type="mrn") | Q(facility__isnull=True),
                name="numbering_mrn_hospital_wide",
                violation_error_message="A patient keeps one MRN in every facility, so the MRN "
                "scheme is always hospital-wide.",
            ),
        ]

    def __str__(self) -> str:
        scope = self.facility.code.upper() if self.facility_id else "hospital-wide"
        return f"{self.get_document_type_display()} ({scope})"

    @property
    def format(self) -> formatting.Format:
        return formatting.Format(
            prefix=self.prefix,
            separator=self.separator,
            include_facility_code=self.include_facility_code,
            period=self.period,
            year_format=self.year_format,
            financial_year_start_month=self.financial_year_start_month,
            padding=self.padding,
        )

    def _fill_organization(self) -> None:
        if not self.organization_id:
            from apps.organizations.selectors import get_deployment_organization

            self.organization_id = get_deployment_organization().pk

    def facility_codes(self) -> list[str]:
        """Facility codes that can appear in this scheme's numbers."""
        from apps.facilities.models import Facility

        if self.facility_id:
            return [self.facility.code]
        return list(Facility.objects.values_list("code", flat=True)) or [""]

    def longest_example(self) -> str:
        """The longest number this scheme can currently produce (for length limits)."""
        from datetime import date

        fmt = self.format
        key = formatting.period_key(fmt, date(2026, 10, 1))
        biggest = 10**self.padding - 1
        return max(
            (
                formatting.format_number(fmt, sequence=biggest, key=key, facility_code=code)
                for code in self.facility_codes()
            ),
            key=len,
        )

    def clean_fields(self, exclude=None):
        self._fill_organization()  # always this deployment's hospital, never client input
        super().clean_fields(exclude)

    def clean(self):
        super().clean()
        self._fill_organization()
        errors = {}
        if self.document_type == self.DocumentType.MRN and self.facility_id:
            errors["facility"] = (
                "A patient keeps one MRN in every facility, so the MRN scheme is hospital-wide."
            )
        if self.padding is not None and not 3 <= self.padding <= 12:
            errors["padding"] = "Use between 3 and 12 digits."
        if (
            self.financial_year_start_month is not None
            and not 1 <= self.financial_year_start_month <= 12
        ):
            errors["financial_year_start_month"] = "Use a month number from 1 to 12."
        if not errors and self._india_invoice() and self.padding:
            example = self.longest_example()
            if len(example) > INDIA_INVOICE_MAX_LENGTH:
                errors["padding"] = (
                    f"GST invoice numbers may have at most {INDIA_INVOICE_MAX_LENGTH} characters; "
                    f"this format can reach {len(example)} ({example}). Use a shorter prefix, "
                    "short year or fewer digits."
                )
        if errors:
            raise ValidationError(errors)

    def _india_invoice(self) -> bool:
        from apps.organizations.models import Organization

        if self.document_type != self.DocumentType.INVOICE:
            return False
        country = (
            Organization.objects.filter(pk=self.organization_id)
            .values_list("country", flat=True)
            .first()
        )
        return country == "IN"

    def save(self, *args, **kwargs):
        self._fill_organization()
        super().save(*args, **kwargs)


class NumberCounter(models.Model):
    """The last running number used, per scheme and period. Locked with SELECT ... FOR UPDATE
    in the transaction that creates the record, so a rolled-back record also gives its number
    back (no gaps, which GST invoice series need) and two requests never get the same number."""

    scheme = models.ForeignKey(NumberingScheme, on_delete=models.PROTECT, related_name="counters")
    period_key = models.CharField(max_length=16, blank=True)
    last_value = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "numbering_counters"
        constraints = [
            models.UniqueConstraint(
                fields=["scheme", "period_key"], name="numbering_counter_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.scheme} {self.period_key or 'all time'}: {self.last_value}"


class IssuedNumber(OrganizationOwnedModel):
    """Register of every number handed out. Append-only; the database refuses duplicates."""

    scheme = models.ForeignKey(NumberingScheme, on_delete=models.PROTECT, related_name="issued")
    document_type = models.CharField(max_length=16, choices=NumberingScheme.DocumentType.choices)
    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    value = models.CharField(max_length=64)
    period_key = models.CharField(max_length=16, blank=True)
    sequence = models.PositiveBigIntegerField()
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    reference = models.CharField(
        max_length=100, blank=True, help_text="What the number was given to, e.g. 'patient:<id>'."
    )

    class Meta:
        db_table = "issued_numbers"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["document_type", "value"], name="issued_number_unique")
        ]
        indexes = [
            models.Index(fields=["document_type", "-created_at"], name="issued_numbers_type_idx")
        ]

    def __str__(self) -> str:
        return self.value
