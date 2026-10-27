"""Issue business numbers and manage numbering schemes (HIMS-ORG-003).

``issue_number`` is what domains call (patient registration, encounters, billing, claims) inside
the transaction that creates their record:

    with transaction.atomic():
        patient = Patient(...)
        patient.mrn = issue_number(document_type="mrn", facility=facility, actor=user,
                                   reference=f"patient:{patient.pk}").value
        patient.save()

The counter row stays locked until that transaction ends, so numbers are handed out strictly in
order, never twice, and a rolled-back record does not leave a gap.
"""

from datetime import date
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services import AuditAction, model_changes, record_audit_event, snapshot
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError, DomainError

from . import formatting
from .models import IssuedNumber, NumberCounter, NumberingScheme

DocumentType = NumberingScheme.DocumentType

UPDATABLE_FIELDS = (
    "prefix",
    "separator",
    "include_facility_code",
    "period",
    "year_format",
    "financial_year_start_month",
    "padding",
    "start_at",
    "is_active",
)

# Created for every hospital if it has no hospital-wide scheme for that type yet. Every value
# can be changed afterwards in the app (Numbering page) or the admin console.
_COMMON = {"separator": "-", "period": NumberingScheme.Period.NONE}
DEFAULT_SCHEMES: dict[str, dict[str, dict]] = {
    "IN": {
        DocumentType.MRN: {**_COMMON, "prefix": "MRN", "padding": 8},
        DocumentType.ENCOUNTER: {
            **_COMMON,
            "prefix": "ENC",
            "period": "calendar_year",
            "padding": 7,
        },
        # INV/26-27/000001: 16 characters, the GST maximum; restarts every April.
        DocumentType.INVOICE: {
            "prefix": "INV",
            "separator": "/",
            "period": "financial_year",
            "year_format": "short",
            "financial_year_start_month": 4,
            "padding": 6,
        },
        DocumentType.CLAIM: {
            **_COMMON,
            "prefix": "CLM",
            "period": "financial_year",
            "financial_year_start_month": 4,
            "padding": 6,
        },
    },
    "US": {
        DocumentType.MRN: {**_COMMON, "prefix": "MRN", "padding": 8},
        DocumentType.ENCOUNTER: {
            **_COMMON,
            "prefix": "ENC",
            "period": "calendar_year",
            "padding": 7,
        },
        DocumentType.INVOICE: {
            **_COMMON,
            "prefix": "INV",
            "period": "calendar_year",
            "financial_year_start_month": 1,
            "padding": 7,
        },
        DocumentType.CLAIM: {
            **_COMMON,
            "prefix": "CLM",
            "period": "calendar_year",
            "financial_year_start_month": 1,
            "padding": 7,
        },
    },
}


class NumberingNotConfigured(ConflictError):
    code = "NUMBERING_NOT_CONFIGURED"
    title = "Numbering not set up"


def ensure_default_schemes(organization) -> list[NumberingScheme]:
    """Create missing hospital-wide schemes with country defaults. Safe to run repeatedly."""
    created = []
    defaults = DEFAULT_SCHEMES.get(organization.country, DEFAULT_SCHEMES["US"])
    for document_type, values in defaults.items():
        exists = NumberingScheme.objects.filter(
            document_type=document_type, facility__isnull=True
        ).exists()
        if exists:
            continue
        scheme = NumberingScheme(organization=organization, document_type=document_type, **values)
        scheme.full_clean()
        scheme.save()
        record_audit_event(
            action=AuditAction.NUMBERING_SCHEME_CREATED,
            resource_type="numbering_scheme",
            resource_id=scheme.pk,
            organization_id=organization.pk,
            changes={"after": snapshot(scheme)},
            metadata={"via": "default"},
        )
        created.append(scheme)
    return created


def local_today(facility=None) -> date:
    """Today's date where the number is issued (facility time zone, else the hospital's)."""
    if facility is not None:
        zone = facility.timezone
    else:
        from apps.organizations.selectors import get_deployment_organization

        zone = get_deployment_organization().default_timezone
    return timezone.now().astimezone(ZoneInfo(zone)).date()


def resolve_scheme(document_type: str, facility=None) -> NumberingScheme:
    """The facility's own active scheme if it has one, otherwise the hospital-wide one."""
    schemes = NumberingScheme.objects.filter(document_type=document_type, is_active=True)
    if facility is not None and document_type != DocumentType.MRN:
        own = schemes.filter(facility=facility).first()
        if own is not None:
            return own
    scheme = schemes.filter(facility__isnull=True).first()
    if scheme is None:
        label = DocumentType(document_type).label
        raise NumberingNotConfigured(
            f"No active numbering scheme for '{label}'. Set one up on the Numbering page."
        )
    return scheme


def _facility_code(scheme: NumberingScheme, facility) -> str:
    if not scheme.include_facility_code:
        return ""
    if facility is None:
        raise DomainError(
            "This numbering scheme includes the facility code, so a facility is required.",
            code="FACILITY_REQUIRED",
        )
    return facility.code


def _first_free(scheme, *, after: int, key: str, code: str) -> tuple[int, str]:
    """Next running number whose formatted value has never been issued.

    A value can already exist only after a format change (e.g. prefix A -> B -> A); skipping it
    keeps every number unique without ever reusing one.
    """
    fmt = scheme.format
    sequence = after
    for _ in range(10_000):
        sequence += 1
        value = formatting.format_number(fmt, sequence=sequence, key=key, facility_code=code)
        taken = IssuedNumber.objects.filter(
            document_type=scheme.document_type, value=value
        ).exists()
        if not taken:
            return sequence, value
    raise ConflictError("Could not find a free number; check the numbering scheme.")


def _counter(scheme: NumberingScheme, key: str) -> NumberCounter:
    # Insert-if-missing without a race, then lock the row until the caller's transaction ends.
    NumberCounter.objects.bulk_create(
        [NumberCounter(scheme=scheme, period_key=key, last_value=scheme.start_at - 1)],
        ignore_conflicts=True,
    )
    return NumberCounter.objects.select_for_update().get(scheme=scheme, period_key=key)


@transaction.atomic
def issue_number(
    *, document_type: str, facility=None, actor=None, reference: str = "", on: date | None = None
) -> IssuedNumber:
    scheme = resolve_scheme(document_type, facility)
    code = _facility_code(scheme, facility)
    key = formatting.period_key(scheme.format, on or local_today(facility))
    counter = _counter(scheme, key)
    sequence, value = _first_free(scheme, after=counter.last_value, key=key, code=code)
    counter.last_value = sequence
    counter.save(update_fields=["last_value", "updated_at"])
    try:
        with transaction.atomic():
            return IssuedNumber.objects.create(
                organization_id=scheme.organization_id,
                scheme=scheme,
                document_type=document_type,
                facility=facility,
                value=value,
                period_key=key,
                sequence=sequence,
                issued_by=actor,
                reference=reference[:100],
            )
    except IntegrityError as exc:  # only possible if the register was edited outside HIMS
        raise ConflictError("That number already exists; try again.") from exc


def next_number_preview(scheme: NumberingScheme, *, facility=None, on: date | None = None) -> str:
    """The number the next record would get, without using it up."""
    facility = facility or scheme.facility
    key = formatting.period_key(scheme.format, on or local_today(facility))
    last = (
        NumberCounter.objects.filter(scheme=scheme, period_key=key)
        .values_list("last_value", flat=True)
        .first()
    )
    code = (facility.code if facility else "EXAMPLE") if scheme.include_facility_code else ""
    after = scheme.start_at - 1 if last is None else last
    return _first_free(scheme, after=after, key=key, code=code)[1]


def example_number(scheme: NumberingScheme, *, on: date | None = None) -> str:
    """What a number looks like with these settings (unsaved schemes too)."""
    fmt = scheme.format
    code = scheme.facility.code if scheme.facility_id else "EXAMPLE"
    key = formatting.period_key(
        fmt, on or local_today(scheme.facility if scheme.facility_id else None)
    )
    return formatting.format_number(
        fmt,
        sequence=scheme.start_at,
        key=key,
        facility_code=code if fmt.include_facility_code else "",
    )


@transaction.atomic
def create_scheme(*, actor, request=None, **data) -> NumberingScheme:
    scheme = NumberingScheme(**data)
    scheme.full_clean()
    scheme.save()
    record_audit_event(
        action=AuditAction.NUMBERING_SCHEME_CREATED,
        resource_type="numbering_scheme",
        resource_id=scheme.pk,
        facility_id=scheme.facility_id,
        actor=actor,
        request=request,
        changes={"after": snapshot(scheme)},
    )
    return scheme


@transaction.atomic
def update_scheme(*, actor, scheme_id, version: int, request=None, **changes) -> NumberingScheme:
    scheme = lock_for_update(NumberingScheme, pk=scheme_id, expected_version=version)
    before = snapshot(scheme, UPDATABLE_FIELDS)
    for field, value in changes.items():
        if field not in UPDATABLE_FIELDS:
            raise ValueError(f"{field} is not updatable")
        setattr(scheme, field, value)
    scheme.full_clean()
    bump_version(scheme)
    scheme.save()
    record_audit_event(
        action=AuditAction.NUMBERING_SCHEME_UPDATED,
        resource_type="numbering_scheme",
        resource_id=scheme.pk,
        facility_id=scheme.facility_id,
        actor=actor,
        request=request,
        changes=model_changes(before, snapshot(scheme, UPDATABLE_FIELDS)),
    )
    return scheme


@transaction.atomic
def set_next_number(
    *, actor, scheme_id, version: int, next_value: int, request=None, on: date | None = None
) -> NumberingScheme:
    """Continue from a previous system, e.g. the old software's last MRN was 54321 -> next 54322.

    Only moves forward: going back could hand out a number that was already used.
    """
    scheme = lock_for_update(NumberingScheme, pk=scheme_id, expected_version=version)
    key = formatting.period_key(scheme.format, on or local_today(scheme.facility))
    counter = _counter(scheme, key)
    current_next = counter.last_value + 1
    if next_value <= counter.last_value:
        raise ConflictError(
            f"The next number can only move forward. It is already {current_next}.",
            code="NUMBER_WOULD_GO_BACKWARDS",
        )
    counter.last_value = next_value - 1
    counter.save(update_fields=["last_value", "updated_at"])
    bump_version(scheme)
    scheme.save(update_fields=["version", "updated_at"])
    record_audit_event(
        action=AuditAction.NUMBERING_NEXT_NUMBER_SET,
        resource_type="numbering_scheme",
        resource_id=scheme.pk,
        facility_id=scheme.facility_id,
        actor=actor,
        request=request,
        changes={"before": {"next": current_next}, "after": {"next": next_value}},
        metadata={"period": key or "all time"},
    )
    return scheme
