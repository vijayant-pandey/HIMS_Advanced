"""Artifact A for patients and the MPI: the rules the database itself keeps (HIMS-DATA-003; spec
28.8, "automated tests for critical invariants").

The services check every rule first and give a plain message. These tests go past the services,
straight to the database (as a bug, a script or a hand-written SQL fix could), and expect the
database to refuse. ``RULES`` names every constraint, unique index and trigger on the patient
tables; the last test fails when a table gains one that is not listed, so a new rule cannot be
added without its test. All people and numbers are invented.
"""

from datetime import timedelta

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.numbering.services import ensure_default_schemes
from apps.patients.models import (
    EmergencyAccess,
    Patient,
    PatientAlias,
    PatientConsent,
    PatientContact,
    PatientIdentifier,
    PatientRelationship,
)
from apps.patients.services import register_patient
from common.datadict.catalog import PATIENT_TABLES

# Every rule on the patient tables -> the test that breaks it.
RULES = {
    # Constraints and unique indexes.
    "patients_mrn_unique": "test_one_mrn_per_patient_in_the_hospital",
    "patients_merged_has_target": "test_a_merged_record_points_at_the_record_kept",
    "patients_not_merged_into_self": "test_a_merged_record_points_at_the_record_kept",
    "patients_restriction_has_kind": "test_a_restricted_record_says_why",
    "patients_version_check": "test_versions_never_go_below_zero",
    "patient_contacts_phone_has_number": "test_a_phone_has_a_number_and_an_email_an_address",
    "patient_contacts_email_has_address": "test_a_phone_has_a_number_and_an_email_an_address",
    "patient_contacts_version_check": "test_versions_never_go_below_zero",
    "patient_relationships_not_self": "test_nobody_is_their_own_relative",
    "patient_relationships_version_check": "test_versions_never_go_below_zero",
    "patient_identifiers_unique_number": "test_one_person_per_id_number",
    "patient_identifiers_version_check": "test_versions_never_go_below_zero",
    "patient_emergency_access_reviewer_not_user": "test_emergency_access_review_rules",
    "patient_emergency_access_review_complete": "test_emergency_access_review_rules",
    "patient_emergency_access_version_check": "test_versions_never_go_below_zero",
    # Triggers.
    "patient_aliases_history": "test_history_rows_never_change_except_by_a_merge",
    "patient_consents_history": "test_history_rows_never_change_except_by_a_merge",
}


@pytest.fixture
def desk(make_user, system_roles, facility_a, organization):
    ensure_default_schemes(organization)
    return make_user(role=system_roles["receptionist"], facility=facility_a)


def _register(desk, facility, given, mobile):
    return register_patient(
        actor=desk,
        facility=facility,
        data={"given_name": given, "family_name": "Invariant", "sex": "female", "age_years": 40},
        mobile=mobile,
        privacy_notice="given",
    )


@pytest.fixture
def two(desk, facility_a):
    return (
        _register(desk, facility_a, "Anvi", "+919876500101"),
        _register(desk, facility_a, "Banu", "+919876500102"),
    )


def _refused(error=IntegrityError):
    """The database must refuse what runs inside (in its own savepoint)."""
    return pytest.raises(error)


@pytest.mark.django_db
def test_one_mrn_per_patient_in_the_hospital(two):
    first, second = two
    with _refused(), transaction.atomic():
        Patient.objects.filter(pk=second.pk).update(mrn=first.mrn)


@pytest.mark.django_db
def test_a_merged_record_points_at_the_record_kept(two):
    first, second = two
    with _refused(), transaction.atomic():
        Patient.objects.filter(pk=first.pk).update(status=Patient.Status.MERGED)
    with _refused(), transaction.atomic():
        Patient.objects.filter(pk=first.pk).update(
            status=Patient.Status.MERGED, merged_into_id=first.pk
        )
    with transaction.atomic():  # the one allowed shape: merged into another record
        Patient.objects.filter(pk=first.pk).update(
            status=Patient.Status.MERGED, merged_into_id=second.pk
        )


@pytest.mark.django_db
def test_a_restricted_record_says_why(two):
    first, _ = two
    with _refused(), transaction.atomic():
        Patient.objects.filter(pk=first.pk).update(is_restricted=True)
    with _refused(), transaction.atomic():
        Patient.objects.filter(pk=first.pk).update(restriction=Patient.Restriction.VIP)


@pytest.mark.django_db
def test_versions_never_go_below_zero(two):
    first, _ = two
    for model, rows in (
        (Patient, Patient.objects.filter(pk=first.pk)),
        (PatientContact, PatientContact.objects.filter(patient=first)),
        (PatientRelationship, PatientRelationship.objects.all()),
        (PatientIdentifier, PatientIdentifier.objects.all()),
        (EmergencyAccess, EmergencyAccess.objects.all()),
    ):
        with _refused(), transaction.atomic():
            # On empty tables a raw UPDATE refuses nothing, so add one row through raw SQL first.
            if not rows.exists():
                _one_row(model, first)
            with connection.cursor() as cursor:
                cursor.execute(f'UPDATE "{model._meta.db_table}" SET version = -1')  # noqa: S608


def _one_row(model, patient):
    common = {"organization_id": patient.organization_id, "patient": patient}
    if model is PatientRelationship:
        model.objects.create(**common, relation="mother", name="Synthetic Mother")
    elif model is PatientIdentifier:
        model.objects.create(
            **common, kind="passport", value_encrypted="x", value_hash="a" * 64, value_display="X"
        )
    elif model is EmergencyAccess:
        model.objects.create(
            **common,
            user=patient.registered_by,
            reason="Synthetic emergency",
            expires_at=timezone.now() + timedelta(hours=4),
        )


@pytest.mark.django_db
def test_a_phone_has_a_number_and_an_email_an_address(two):
    first, _ = two
    with _refused(), transaction.atomic():
        PatientContact.objects.filter(patient=first, kind="mobile").update(phone="")
    with _refused(), transaction.atomic():
        PatientContact.objects.create(
            organization_id=first.organization_id, patient=first, kind="email", email=""
        )


@pytest.mark.django_db
def test_nobody_is_their_own_relative(two):
    first, second = two
    with _refused(), transaction.atomic():
        PatientRelationship.objects.create(
            organization_id=first.organization_id,
            patient=first,
            relation="sibling",
            name="Synthetic Self",
            related_patient=first,
        )
    PatientRelationship.objects.create(  # another patient is fine
        organization_id=first.organization_id,
        patient=first,
        relation="sibling",
        name="Banu Invariant",
        related_patient=second,
    )


@pytest.mark.django_db
def test_one_person_per_id_number(two):
    first, second = two

    def number(patient, kind, **extra):
        return PatientIdentifier.objects.create(
            organization_id=patient.organization_id,
            patient=patient,
            kind=kind,
            value_encrypted="synthetic",
            value_hash="b" * 64,
            value_display="XXXX XXXX 0001",
            **extra,
        )

    number(first, "aadhaar")
    with _refused(), transaction.atomic():
        number(second, "aadhaar")
    # An ended number may be recorded again, and kinds outside UNIQUE_IDENTIFIER_KINDS (voter
    # ID, driving licence, previous MRN) are not refused by the database.
    number(second, "aadhaar", is_active=False)
    number(first, "voter_id")
    number(second, "voter_id")


@pytest.mark.django_db
def test_emergency_access_review_rules(desk, two):
    first, _ = two
    access = EmergencyAccess.objects.create(
        organization_id=first.organization_id,
        patient=first,
        user=desk,
        reason="Synthetic emergency",
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    rows = EmergencyAccess.objects.filter(pk=access.pk)
    with _refused(), transaction.atomic():
        rows.update(reviewed_by=desk, reviewed_at=timezone.now(), outcome="appropriate")
    with _refused(), transaction.atomic():
        rows.update(reviewed_at=timezone.now())  # a review without its outcome
    with _refused(), transaction.atomic():
        rows.update(outcome="appropriate")  # an outcome without its time


@pytest.mark.django_db
def test_history_rows_never_change_except_by_a_merge(desk, two):
    first, second = two
    PatientAlias.objects.create(
        organization_id=first.organization_id, patient=first, kind="previous_name", given_name="A"
    )
    for model in (PatientAlias, PatientConsent):
        rows = model.objects.filter(patient=first)
        assert rows.exists()
        with _refused(DatabaseError), transaction.atomic():
            rows.update(created_at=timezone.now() - timedelta(days=1))
        with _refused(DatabaseError), transaction.atomic():
            rows.delete()
        # A merge (HIMS-PAT-004) moves the history to the record kept: patient_id alone.
        with transaction.atomic():
            rows.update(patient=second)
        assert model.objects.filter(patient=second).exists()


@pytest.mark.django_db
def test_patients_and_their_records_are_never_deleted(two):
    first, _ = two
    with pytest.raises(ProtectedError):
        first.delete()
    # Past Django too: the database's own foreign keys refuse it.
    with _refused(), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute("DELETE FROM patients WHERE id = %s", [first.pk])


@pytest.mark.django_db
def test_every_database_rule_on_the_patient_tables_has_a_test():
    tables = sorted(PATIENT_TABLES)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.conname FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE t.relname = ANY(%s) AND c.contype IN ('c', 'u', 'x')",
            [tables],
        )
        found = {name for (name,) in cursor.fetchall()}
        cursor.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = ANY(%s) "
            "AND indexdef LIKE 'CREATE UNIQUE INDEX%%' AND indexname NOT LIKE '%%_pkey'",
            [tables],
        )
        found |= {name for (name,) in cursor.fetchall()}
        cursor.execute(
            "SELECT tg.tgname FROM pg_trigger tg JOIN pg_class t ON t.oid = tg.tgrelid "
            "WHERE t.relname = ANY(%s) AND NOT tg.tgisinternal",
            [tables],
        )
        found |= {name for (name,) in cursor.fetchall()}
    missing = found - set(RULES)
    assert not missing, f"Add a test that breaks each new rule, and list it in RULES: {missing}"
    gone = set(RULES) - found
    assert not gone, f"These rules are no longer in the database: {gone}"
    names = {name for name in globals() if name.startswith("test_")}
    assert set(RULES.values()) <= names
