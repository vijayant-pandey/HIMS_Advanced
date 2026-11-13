"""Patient registration and the patient record (spec 4.5; HIMS-PAT-001).

Rules: docs/p0/phase-2-patients/01-functional-requirements.md section 1 (approved for now,
2026-11-08). Every change is audited with before/after values in the same transaction; ID
numbers appear in the audit log only masked. Registration issues the MRN in the same
transaction (numbering, HIMS-ORG-003), so a failed registration never uses up a number and a
retried one (same Idempotency-Key) never gets a second.

Who may do what: ``patients.register`` at the facility of registration; edits need the same
permission anywhere in the hospital (one MRN in every facility). Viewing is in the API.
"""

import re
from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services import AuditAction, model_changes, record_audit_event, snapshot
from apps.numbering.services import issue_number
from apps.organizations.dates import hospital_today
from apps.organizations.selectors import get_deployment_organization
from common import crypto
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError, DomainError
from common.outbox.services import publish_event

from . import demographics, identifiers
from .demographics import InvalidValue
from .models import (
    UNIQUE_IDENTIFIER_KINDS,
    Patient,
    PatientAlias,
    PatientConsent,
    PatientContact,
    PatientIdentifier,
    PatientRelationship,
)

ADULT_AGE = 18
GUARDIAN_RELATIONS = {
    PatientRelationship.Relation.MOTHER,
    PatientRelationship.Relation.FATHER,
    PatientRelationship.Relation.GUARDIAN,
}
NAME_FIELDS = ("title", "given_name", "middle_name", "family_name", "preferred_name")
EDITABLE_FIELDS = (
    *NAME_FIELDS,
    "date_of_birth",
    "birth_date_estimated",
    "sex",
    "gender_identity",
    "pronouns",
    "preferred_language",
    "marital_status",
    "occupation",
    "blood_group_reported",
    "has_no_phone",
    "is_unknown",
    "identification_note",
)
CONTACT_FIELDS = (
    "phone",
    "email",
    "address_line1",
    "address_line2",
    "city",
    "district",
    "state",
    "postal_code",
    "country",
    "is_primary",
    "is_active",
)
RELATIONSHIP_FIELDS = (
    "relation",
    "name",
    "phone",
    "is_legal_guardian",
    "is_emergency_contact",
    "related_patient",
    "note",
    "is_active",
)
_POSTAL = {"IN": r"^\d{6}$", "US": r"^\d{5}(-\d{4})?$"}


class DuplicateIdentifier(ConflictError):
    code = "DUPLICATE_IDENTIFIER"
    title = "ID number already recorded"


class PatientMerged(ConflictError):
    code = "PATIENT_MERGED"
    title = "Record merged"


def _country() -> str:
    return get_deployment_organization().country


def _invalid(field: str, exc: Exception) -> ValidationError:
    return ValidationError({field: str(exc)})


def _audit(action, patient, *, actor, request, changes=None, reason="", metadata=None):
    record_audit_event(
        action=action,
        resource_type="patient",
        resource_id=patient.pk,
        facility_id=patient.registered_facility_id,
        actor=actor,
        request=request,
        changes=changes or {},
        reason=reason,
        metadata=metadata or {},
    )


def _refuse_if_merged(patient: Patient) -> None:
    if patient.status == Patient.Status.MERGED:
        raise PatientMerged("This record was merged into another one; change that record instead.")


# --- Checking what the front desk typed -------------------------------------------------------


def _clean_names(data: dict, *, unknown: bool) -> None:
    labels = {
        "title": "Title",
        "given_name": "Given name",
        "middle_name": "Middle name",
        "family_name": "Family name",
        "preferred_name": "Preferred name",
    }
    for field, label in labels.items():
        if field in data:
            try:
                data[field] = demographics.clean_name(
                    data[field], label=label, required=field == "given_name" and not unknown
                )
            except InvalidValue as exc:
                raise _invalid(field, exc) from exc
    if unknown and not data.get("given_name"):
        data["given_name"] = "Unknown"


def _birth(data: dict, today: date) -> None:
    """Fill date_of_birth / birth_date_estimated from a date or an age (D2)."""
    ages = {k: data.pop(k, None) for k in ("age_years", "age_months", "age_days")}
    if data.get("date_of_birth"):
        data["birth_date_estimated"] = bool(data.get("birth_date_estimated", False))
    else:
        try:
            data["date_of_birth"] = demographics.estimated_date_of_birth(
                today, years=ages["age_years"], months=ages["age_months"], days=ages["age_days"]
            )
        except InvalidValue as exc:
            raise _invalid("date_of_birth", exc) from exc
        data["birth_date_estimated"] = True
    try:
        demographics.check_date_of_birth(data["date_of_birth"], today)
    except InvalidValue as exc:
        raise _invalid("date_of_birth", exc) from exc


def _phone(value: str, field: str, *, country: str, mobile: bool = False) -> str:
    try:
        return demographics.normalise_phone(value, country=country, mobile=mobile)
    except InvalidValue as exc:
        raise _invalid(field, exc) from exc


def _check_address(values: dict, *, country: str, prefix: str = "") -> None:
    if not values.get("state", "").strip():
        raise ValidationError({f"{prefix}state": "Give the state."})
    pattern = _POSTAL.get(values.get("country") or country)
    code = values.get("postal_code", "").strip()
    if code and pattern and not re.match(pattern, code):
        label = "PIN code (6 digits)" if (values.get("country") or country) == "IN" else "ZIP code"
        raise ValidationError({f"{prefix}postal_code": f"Enter a valid {label}."})


def _identifier_row(patient, item: dict, *, actor, country: str, field: str) -> PatientIdentifier:
    kind = item["kind"]
    try:
        number = identifiers.check(kind, item["value"], country=country)
    except identifiers.InvalidIdentifier as exc:
        raise _invalid(field, exc) from exc
    issuer = (item.get("issuer") or "").strip()
    if identifiers.RULES[kind].needs_issuer and not issuer:
        raise ValidationError({field: "Say which hospital this MRN is from."})
    value_hash = identifiers.fingerprint(kind, number, issuer=issuer)
    if kind in UNIQUE_IDENTIFIER_KINDS:
        other = (
            PatientIdentifier.objects.filter(kind=kind, value_hash=value_hash, is_active=True)
            .select_related("patient")
            .first()
        )
        if other is not None:
            same = patient is not None and other.patient_id == patient.pk
            raise DuplicateIdentifier(
                "This patient already has this number."
                if same
                else f"This {PatientIdentifier.Kind(kind).label} is already recorded for patient "
                f"{other.patient.mrn}. Open that record instead of registering again."
            )
    return PatientIdentifier(
        organization_id=patient.organization_id,
        patient=patient,
        kind=kind,
        value_encrypted=crypto.encrypt(number),
        value_hash=value_hash,
        value_display=identifiers.mask(kind, number),
        issuer=issuer,
        valid_until=item.get("valid_until"),
        created_by=actor,
    )


def _save_identifier(row: PatientIdentifier) -> PatientIdentifier:
    try:
        with transaction.atomic():
            row.save()
    except IntegrityError as exc:  # registered by someone else at the same moment
        raise DuplicateIdentifier(
            "This number was just recorded for another patient. Search for it first."
        ) from exc
    return row


def _identifier_audit(row: PatientIdentifier) -> dict:
    """What the audit log keeps of an ID number: never the number itself."""
    return {
        "kind": row.kind,
        "value": row.value_display,
        "issuer": row.issuer,
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
    }


def _needs_guardian(patient: Patient, today: date) -> bool:
    return (
        not patient.is_unknown
        and demographics.years_between(patient.date_of_birth, today) < ADULT_AGE
    )


def _has_guardian(relationships: list[dict]) -> bool:
    return any(
        r.get("is_legal_guardian") or r.get("relation") in GUARDIAN_RELATIONS for r in relationships
    )


# --- Registration -------------------------------------------------------------------------------


@transaction.atomic
def register_patient(
    *,
    actor,
    facility,
    data: dict,
    mobile: str = "",
    alternate_phone: str = "",
    email: str = "",
    address: dict | None = None,
    relationships: list[dict] | None = None,
    identifier_items: list[dict] | None = None,
    privacy_notice: str = "",
    sms_consent: bool | None = None,
    email_consent: bool | None = None,
    consent_method: str = PatientConsent.Method.VERBAL,
    no_guardian_reason: str = "",
    request=None,
) -> Patient:
    """Register a new patient and issue the MRN, all in one transaction.

    ``data`` holds the patient's own fields (names, birth date or age, sex...). The MRN scheme
    missing refuses the whole registration with nothing saved (P0 part 01, section 10).
    """
    organization = get_deployment_organization()
    country = organization.country
    today = hospital_today(facility)
    data = dict(data)
    relationships = relationships or []
    identifier_items = identifier_items or []
    unknown = bool(data.get("is_unknown"))

    _clean_names(data, unknown=unknown)
    _birth(data, today)
    if unknown and not (data.get("identification_note") or "").strip():
        raise ValidationError(
            {"identification_note": "Say how the unknown patient arrived (who brought them)."}
        )
    mobile = _phone(mobile, "mobile", country=country, mobile=True)
    if not mobile and not data.get("has_no_phone") and not unknown:
        raise ValidationError({"mobile": "Enter a mobile number, or tick 'No phone'."})
    if mobile:
        data["has_no_phone"] = False
    alternate_phone = _phone(alternate_phone, "alternate_phone", country=country)
    address = {k: (v or "").strip() for k, v in (address or {}).items()}
    has_address = any(address.get(k) for k in ("address_line1", "city", "state", "postal_code"))
    if has_address:
        _check_address(address, country=country)
    for n, relation in enumerate(relationships):
        relation["phone"] = _phone(
            relation.get("phone", ""), f"relationships[{n}].phone", country=country
        )
        relation["name"] = " ".join((relation.get("name") or "").split())
        if not relation["name"]:
            raise ValidationError({f"relationships[{n}].name": "Give the person's name."})

    patient = Patient(
        organization=organization,
        registered_facility=facility,
        registered_by=actor,
        **data,
    )
    patient.search_name = demographics.search_name(*(getattr(patient, f) for f in NAME_FIELDS[1:]))
    no_guardian = _needs_guardian(patient, today) and not _has_guardian(relationships)
    if no_guardian and not no_guardian_reason.strip():
        raise ValidationError(
            {
                "relationships": "A patient under 18 needs a parent or guardian. Add one, or say "
                "why not (e.g. emergency, guardian on the way)."
            }
        )
    # The MRN comes last before saving, so every check above runs before a number is used.
    patient.mrn = issue_number(
        document_type="mrn", facility=facility, actor=actor, reference=f"patient:{patient.pk}"
    ).value
    patient.save()

    contacts = []
    if mobile:
        contacts.append({"kind": PatientContact.Kind.MOBILE, "phone": mobile, "is_primary": True})
    if alternate_phone:
        contacts.append({"kind": PatientContact.Kind.PHONE, "phone": alternate_phone})
    if email:
        contacts.append(
            {"kind": PatientContact.Kind.EMAIL, "email": email.strip(), "is_primary": True}
        )
    if has_address:
        address["country"] = address.get("country") or country
        contacts.append({"kind": PatientContact.Kind.ADDRESS, "is_primary": True, **address})
    for item in contacts:
        PatientContact.objects.create(
            organization=organization, patient=patient, created_by=actor, **item
        )
    for item in relationships:
        PatientRelationship.objects.create(
            organization=organization, patient=patient, created_by=actor, **item
        )
    saved_ids = []
    for n, item in enumerate(identifier_items):
        row = _identifier_row(
            patient, item, actor=actor, country=country, field=f"identifiers[{n}].value"
        )
        saved_ids.append(_save_identifier(row))
    consents = []
    if privacy_notice:
        consents.append((PatientConsent.Kind.PRIVACY_NOTICE, privacy_notice))
    if sms_consent is not None:
        consents.append((PatientConsent.Kind.SMS, "given" if sms_consent else "refused"))
    if email_consent is not None:
        consents.append((PatientConsent.Kind.EMAIL, "given" if email_consent else "refused"))
    for kind, status in consents:
        PatientConsent.objects.create(
            organization=organization,
            patient=patient,
            kind=kind,
            status=status,
            method=consent_method,
            recorded_by=actor,
        )

    after = snapshot(patient, ("mrn", *EDITABLE_FIELDS, "registered_facility"))
    _audit(
        AuditAction.PATIENT_REGISTERED,
        patient,
        actor=actor,
        request=request,
        changes={
            "after": {
                **after,
                "contacts": [c["kind"] for c in contacts],
                "relationships": [r["relation"] for r in relationships],
                "identifiers": [_identifier_audit(row) for row in saved_ids],
                "consents": dict(consents),
            }
        },
        reason=no_guardian_reason.strip() if no_guardian else "",
        metadata={"under_18_without_guardian": True} if no_guardian else {},
    )
    # Ids only: no names or numbers leave in events (spec 13.3).
    publish_event(
        event_type="patient.registered",
        aggregate_type="patient",
        aggregate_id=patient.pk,
        facility_id=facility.pk,
        payload={"patient_id": str(patient.pk), "facility_id": str(facility.pk)},
    )
    return patient


# --- Changes to the record ----------------------------------------------------------------------


@transaction.atomic
def update_patient(*, actor, patient_id, version: int, request=None, **changes) -> Patient:
    """Correct demographics. A changed name keeps the old one as an alias (still searchable)."""
    patient = lock_for_update(Patient, pk=patient_id, expected_version=version)
    _refuse_if_merged(patient)
    for field in changes:
        if field not in EDITABLE_FIELDS:
            raise ValueError(f"{field} is not editable")
    today = hospital_today(patient.registered_facility)
    unknown = changes.get("is_unknown", patient.is_unknown)
    if any(f in changes for f in NAME_FIELDS):
        _clean_names(changes, unknown=unknown)
    if "date_of_birth" in changes:
        try:
            demographics.check_date_of_birth(changes["date_of_birth"], today)
        except InvalidValue as exc:
            raise _invalid("date_of_birth", exc) from exc
    before = snapshot(patient, EDITABLE_FIELDS)
    old_name = {f: getattr(patient, f) for f in ("given_name", "middle_name", "family_name")}
    for field, value in changes.items():
        setattr(patient, field, value)
    if patient.is_unknown and not patient.identification_note.strip():
        raise ValidationError({"identification_note": "Say how the unknown patient arrived."})
    new_name = {f: getattr(patient, f) for f in old_name}
    if new_name != old_name and not before["is_unknown"]:
        PatientAlias.objects.create(
            organization_id=patient.organization_id,
            patient=patient,
            kind=PatientAlias.Kind.PREVIOUS_NAME,
            recorded_by=actor,
            **old_name,
        )
    aliases = patient.aliases.filter(kind=PatientAlias.Kind.PREVIOUS_NAME).values_list(
        "given_name", "middle_name", "family_name"
    )
    patient.search_name = demographics.search_name(
        *(getattr(patient, f) for f in NAME_FIELDS[1:]), *(n for row in aliases for n in row)
    )
    after = snapshot(patient, EDITABLE_FIELDS)
    if after == before:
        return patient
    bump_version(patient)
    patient.save()
    _audit(
        AuditAction.PATIENT_UPDATED,
        patient,
        actor=actor,
        request=request,
        changes=model_changes(before, after),
    )
    return patient


def _patient_for_change(patient_id) -> Patient:
    patient = Patient.objects.select_for_update().get(pk=patient_id)
    _refuse_if_merged(patient)
    return patient


def _clean_contact(kind: str, values: dict, *, country: str) -> dict:
    values = {k: (v.strip() if isinstance(v, str) else v) for k, v in values.items()}
    if kind in (PatientContact.Kind.MOBILE, PatientContact.Kind.PHONE):
        values["phone"] = _phone(
            values.get("phone", ""), "phone", country=country, mobile=kind == "mobile"
        )
        if not values["phone"]:
            raise ValidationError({"phone": "Enter the phone number."})
    elif kind == PatientContact.Kind.EMAIL:
        if not values.get("email"):
            raise ValidationError({"email": "Enter the email address."})
    elif kind == PatientContact.Kind.ADDRESS:
        values["country"] = values.get("country") or country
        _check_address(values, country=country)
    return values


def _one_primary(contact: PatientContact) -> None:
    if contact.is_primary and contact.is_active:
        PatientContact.objects.filter(
            patient_id=contact.patient_id, kind=contact.kind, is_primary=True
        ).exclude(pk=contact.pk).update(is_primary=False)


@transaction.atomic
def add_contact(*, actor, patient_id, kind: str, request=None, **values) -> PatientContact:
    patient = _patient_for_change(patient_id)
    values = _clean_contact(kind, values, country=_country())
    has_primary = patient.contacts.filter(kind=kind, is_active=True, is_primary=True).exists()
    values["is_primary"] = values.get("is_primary", False) or not has_primary
    contact = PatientContact.objects.create(
        organization_id=patient.organization_id,
        patient=patient,
        kind=kind,
        created_by=actor,
        **values,
    )
    _one_primary(contact)
    if kind == PatientContact.Kind.MOBILE and patient.has_no_phone:
        patient.has_no_phone = False
        bump_version(patient)
        patient.save(update_fields=["has_no_phone", "version", "updated_at"])
    _audit(
        AuditAction.PATIENT_CONTACT_ADDED,
        patient,
        actor=actor,
        request=request,
        changes={"after": snapshot(contact, ("kind", *CONTACT_FIELDS))},
    )
    return contact


@transaction.atomic
def update_contact(*, actor, contact_id, version: int, request=None, **changes) -> PatientContact:
    """Correct a contact, make it the main one, or end it (``is_active`` False: kept)."""
    contact = lock_for_update(PatientContact, pk=contact_id, expected_version=version)
    patient = _patient_for_change(contact.patient_id)
    before = snapshot(contact, CONTACT_FIELDS)
    values = {f: getattr(contact, f) for f in CONTACT_FIELDS}
    values.update(changes)
    values = _clean_contact(contact.kind, values, country=_country())
    for field in CONTACT_FIELDS:
        setattr(contact, field, values[field])
    if not contact.is_active:
        contact.is_primary = False
    after = snapshot(contact, CONTACT_FIELDS)
    if after == before:
        return contact
    bump_version(contact)
    contact.save()
    _one_primary(contact)
    _audit(
        AuditAction.PATIENT_CONTACT_UPDATED,
        patient,
        actor=actor,
        request=request,
        changes=model_changes(before, after),
        metadata={"contact_id": str(contact.pk), "kind": contact.kind},
    )
    return contact


def _clean_relationship(values: dict, *, patient: Patient) -> dict:
    values = dict(values)
    if "name" in values:
        values["name"] = " ".join((values["name"] or "").split())
        if not values["name"]:
            raise ValidationError({"name": "Give the person's name."})
    if "phone" in values:
        values["phone"] = _phone(values["phone"], "phone", country=_country())
    related = values.get("related_patient")
    if related is not None and related.pk == patient.pk:
        raise ValidationError({"related_patient": "A patient cannot be their own relative."})
    return values


@transaction.atomic
def add_relationship(*, actor, patient_id, request=None, **values) -> PatientRelationship:
    patient = _patient_for_change(patient_id)
    values = _clean_relationship(values, patient=patient)
    relationship = PatientRelationship.objects.create(
        organization_id=patient.organization_id, patient=patient, created_by=actor, **values
    )
    _audit(
        AuditAction.PATIENT_RELATIONSHIP_ADDED,
        patient,
        actor=actor,
        request=request,
        changes={"after": snapshot(relationship, RELATIONSHIP_FIELDS)},
    )
    return relationship


@transaction.atomic
def update_relationship(
    *, actor, relationship_id, version: int, request=None, **changes
) -> PatientRelationship:
    relationship = lock_for_update(
        PatientRelationship, pk=relationship_id, expected_version=version
    )
    patient = _patient_for_change(relationship.patient_id)
    changes = _clean_relationship(changes, patient=patient)
    before = snapshot(relationship, RELATIONSHIP_FIELDS)
    for field, value in changes.items():
        if field not in RELATIONSHIP_FIELDS:
            raise ValueError(f"{field} is not editable")
        setattr(relationship, field, value)
    after = snapshot(relationship, RELATIONSHIP_FIELDS)
    if after == before:
        return relationship
    bump_version(relationship)
    relationship.save()
    _audit(
        AuditAction.PATIENT_RELATIONSHIP_UPDATED,
        patient,
        actor=actor,
        request=request,
        changes=model_changes(before, after),
        metadata={"relationship_id": str(relationship.pk)},
    )
    return relationship


@transaction.atomic
def add_identifier(
    *, actor, patient_id, kind: str, value: str, issuer: str = "", valid_until=None, request=None
) -> PatientIdentifier:
    patient = _patient_for_change(patient_id)
    row = _identifier_row(
        patient,
        {"kind": kind, "value": value, "issuer": issuer, "valid_until": valid_until},
        actor=actor,
        country=_country(),
        field="value",
    )
    _save_identifier(row)
    _audit(
        AuditAction.PATIENT_IDENTIFIER_ADDED,
        patient,
        actor=actor,
        request=request,
        changes={"after": _identifier_audit(row)},
    )
    return row


@transaction.atomic
def end_identifier(
    *, actor, identifier_id, version: int, reason: str, request=None
) -> PatientIdentifier:
    """A wrong or replaced number is ended with a reason (kept, never deleted); the same number
    can then be recorded on the right patient."""
    row = lock_for_update(PatientIdentifier, pk=identifier_id, expected_version=version)
    patient = _patient_for_change(row.patient_id)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "Say why this number is ended (e.g. typing mistake)."})
    if not row.is_active:
        raise ConflictError("This number is already ended.", code="ALREADY_ENDED")
    row.is_active = False
    row.ended_at = timezone.now()
    row.ended_by = actor
    row.end_reason = reason[:255]
    bump_version(row)
    row.save()
    _audit(
        AuditAction.PATIENT_IDENTIFIER_ENDED,
        patient,
        actor=actor,
        request=request,
        changes={
            "before": _identifier_audit(row) | {"is_active": True},
            "after": {"is_active": False},
        },
        reason=reason,
    )
    return row


@transaction.atomic
def record_consent(
    *, actor, patient_id, kind: str, status: str, method: str, note: str = "", request=None
) -> PatientConsent:
    """A new decision for one kind of consent; earlier decisions stay as history (D9)."""
    patient = _patient_for_change(patient_id)
    previous = current_consents(patient).get(kind)
    if status == PatientConsent.Status.WITHDRAWN and (
        previous is None or previous.status != PatientConsent.Status.GIVEN
    ):
        raise DomainError(
            "Only consent that was given can be withdrawn.", code="NOTHING_TO_WITHDRAW"
        )
    consent = PatientConsent.objects.create(
        organization_id=patient.organization_id,
        patient=patient,
        kind=kind,
        status=status,
        method=method,
        note=(note or "").strip()[:255],
        recorded_by=actor,
    )
    _audit(
        AuditAction.PATIENT_CONSENT_RECORDED,
        patient,
        actor=actor,
        request=request,
        changes={
            "before": {kind: previous.status if previous else None},
            "after": {kind: status},
        },
        metadata={"method": method},
    )
    return consent


def current_consents(patient: Patient) -> dict[str, PatientConsent]:
    """The latest decision for each kind of consent."""
    latest: dict[str, PatientConsent] = {}
    for consent in patient.consents.order_by("-created_at"):
        latest.setdefault(consent.kind, consent)
    return latest


def record_viewed(patient: Patient, *, actor, request) -> None:
    """Opening a patient's record is audited (spec 13.4: 'viewing a patient record')."""
    _audit(AuditAction.PATIENT_RECORD_VIEWED, patient, actor=actor, request=request)
