"""Patients and their master record (spec 4.5, 9; HIMS-PAT-001).

Design: docs/p0/phase-2-patients/02-database-design.md (approved for now, 2026-11-08). The UUID
is the record's identity; the MRN is the hospital-facing number, issued once from the hospital's
MRN numbering scheme and never changed (spec 4.5). Nothing here is ever deleted: contacts,
relationships and ID numbers are ended, consents get a new row, names keep their old spelling
as an alias (spec 28.2).

Clinical tables (visits, allergies, diagnoses, notes) come in later Phase 2 tickets; duplicate
detection, merging and restricted records too (HIMS-PAT-003, -004, -006).
"""

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from common.models import OrganizationOwnedModel, UUIDPrimaryKeyModel, VersionedModel


class Sex(models.TextChoices):
    MALE = "male", "Male"
    FEMALE = "female", "Female"
    INTERSEX = "intersex", "Intersex"
    UNKNOWN = "unknown", "Unknown"


class Patient(OrganizationOwnedModel, VersionedModel):
    """One person who is, or was, a patient of the hospital: one MRN in every facility."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        MERGED = "merged", "Merged into another record"

    class MaritalStatus(models.TextChoices):
        SINGLE = "single", "Single"
        MARRIED = "married", "Married"
        DIVORCED = "divorced", "Divorced"
        SEPARATED = "separated", "Separated"
        WIDOWED = "widowed", "Widowed"
        OTHER = "other", "Other"

    class BloodGroup(models.TextChoices):
        A_POS = "A+", "A+"
        A_NEG = "A-", "A-"
        B_POS = "B+", "B+"
        B_NEG = "B-", "B-"
        O_POS = "O+", "O+"
        O_NEG = "O-", "O-"
        AB_POS = "AB+", "AB+"
        AB_NEG = "AB-", "AB-"

    mrn = models.CharField(
        max_length=40, editable=False, help_text="Issued by the MRN numbering scheme; never changes"
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE, editable=False
    )
    merged_into = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="+",
        help_text="Set only by a completed merge (HIMS-PAT-004).",
    )
    title = models.CharField(max_length=20, blank=True)
    given_name = models.CharField(max_length=150, help_text="One name is enough")
    middle_name = models.CharField(max_length=150, blank=True)
    family_name = models.CharField(max_length=150, blank=True)
    preferred_name = models.CharField(max_length=150, blank=True)
    date_of_birth = models.DateField()
    birth_date_estimated = models.BooleanField(
        default=False, help_text="Entered as an age, so the date is approximate"
    )
    sex = models.CharField(max_length=16, choices=Sex.choices)
    gender_identity = models.CharField(max_length=60, blank=True)
    pronouns = models.CharField(max_length=60, blank=True)
    preferred_language = models.CharField(max_length=35, blank=True, help_text="e.g. hi, en-US")
    marital_status = models.CharField(max_length=30, choices=MaritalStatus.choices, blank=True)
    occupation = models.CharField(max_length=100, blank=True)
    blood_group_reported = models.CharField(
        max_length=5,
        choices=BloodGroup.choices,
        blank=True,
        help_text="As the patient says; not a laboratory result",
    )
    has_no_phone = models.BooleanField(
        default=False, help_text="The patient has no phone (ticked instead of a mobile number)"
    )
    is_unknown = models.BooleanField(
        default=False, help_text="Registered as unknown or unconscious; details completed later"
    )
    identification_note = models.CharField(
        max_length=255,
        blank=True,
        help_text="For an unknown patient: how they arrived, e.g. 'Brought by ambulance, MG Road'",
    )
    registered_facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.PROTECT, related_name="+"
    )
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    search_name = models.CharField(
        max_length=500,
        editable=False,
        help_text="All names (and earlier names) in lower case, for patient search",
    )

    class Meta:
        db_table = "patients"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "mrn"], name="patients_mrn_unique"),
            models.CheckConstraint(
                condition=~Q(status="merged") | Q(merged_into__isnull=False),
                name="patients_merged_has_target",
            ),
            models.CheckConstraint(
                condition=Q(merged_into__isnull=True) | ~Q(merged_into=F("id")),
                name="patients_not_merged_into_self",
            ),
        ]
        indexes = [
            models.Index(fields=["date_of_birth"], name="patients_dob_idx"),
            models.Index(
                fields=["registered_facility", "-created_at"], name="patients_facility_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.mrn} {self.full_name}"

    @property
    def full_name(self) -> str:
        parts = (self.title, self.given_name, self.middle_name, self.family_name)
        return " ".join(part for part in parts if part)


class PatientAlias(UUIDPrimaryKeyModel):
    """An earlier name (or, after a merge, an earlier MRN) that still finds the patient.

    Append-only: a database trigger refuses changes and deletes.
    """

    class Kind(models.TextChoices):
        PREVIOUS_NAME = "previous_name", "Previous name"
        MERGED_MRN = "merged_mrn", "MRN of a merged record"
        OTHER_NAME = "other_name", "Other name"

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="aliases")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    given_name = models.CharField(max_length=150, blank=True)
    middle_name = models.CharField(max_length=150, blank=True)
    family_name = models.CharField(max_length=150, blank=True)
    mrn = models.CharField(max_length=40, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "patient_aliases"
        ordering = ["-created_at"]
        verbose_name_plural = "patient aliases"

    def __str__(self) -> str:
        name = " ".join(p for p in (self.given_name, self.middle_name, self.family_name) if p)
        return name or self.mrn


class PatientContact(OrganizationOwnedModel, VersionedModel):
    """A way to reach the patient: a mobile or other phone, an email or an address."""

    class Kind(models.TextChoices):
        MOBILE = "mobile", "Mobile"
        PHONE = "phone", "Other phone"
        EMAIL = "email", "Email"
        ADDRESS = "address", "Address"

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="contacts")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    phone = models.CharField(
        max_length=16, blank=True, help_text="International format (E.164), e.g. +919876543210"
    )
    email = models.EmailField(blank=True)
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True, help_text="District (IN) / county (US)")
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=10, blank=True)
    country = models.CharField(max_length=2, blank=True)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, help_text="Ended contacts are kept, not deleted")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "patient_contacts"
        ordering = ["kind", "-is_primary", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(kind__in=["mobile", "phone"]) | ~Q(phone=""),
                name="patient_contacts_phone_has_number",
            ),
            models.CheckConstraint(
                condition=~Q(kind="email") | ~Q(email=""),
                name="patient_contacts_email_has_address",
            ),
        ]
        indexes = [models.Index(fields=["phone"], name="patient_contacts_phone_idx")]

    def __str__(self) -> str:
        if self.kind == self.Kind.EMAIL:
            return self.email
        if self.kind == self.Kind.ADDRESS:
            return ", ".join(p for p in (self.address_line1, self.city, self.state) if p)
        return self.phone


class PatientRelationship(OrganizationOwnedModel, VersionedModel):
    """A guardian, parent, next of kin, emergency contact or caregiver of the patient."""

    class Relation(models.TextChoices):
        MOTHER = "mother", "Mother"
        FATHER = "father", "Father"
        GUARDIAN = "guardian", "Guardian"
        SPOUSE = "spouse", "Spouse / partner"
        CHILD = "child", "Son / daughter"
        SIBLING = "sibling", "Brother / sister"
        NEXT_OF_KIN = "next_of_kin", "Next of kin"
        CAREGIVER = "caregiver", "Caregiver"
        EMERGENCY_CONTACT = "emergency_contact", "Emergency contact"
        OTHER = "other", "Other"

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="relationships")
    relation = models.CharField(max_length=20, choices=Relation.choices)
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=16, blank=True, help_text="International format (E.164)")
    is_legal_guardian = models.BooleanField(default=False)
    is_emergency_contact = models.BooleanField(default=False)
    related_patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="When this person is also a patient here",
    )
    note = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True, help_text="Ended relationships are kept")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "patient_relationships"
        ordering = ["-is_active", "-is_legal_guardian", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(related_patient__isnull=True) | ~Q(related_patient=F("patient")),
                name="patient_relationships_not_self",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_relation_display()})"


# Kinds that belong to one person only: the same number on a second patient is refused.
UNIQUE_IDENTIFIER_KINDS = ("abha_number", "abha_address", "aadhaar", "passport", "ssn")


class PatientIdentifier(OrganizationOwnedModel, VersionedModel):
    """An identity document number: stored encrypted, shown masked, found by a keyed fingerprint.

    The full number is never shown, logged or put in the audit log (spec 13.3; decisions D6, D7:
    Aadhaar and SSN may be entered, not verified yet, encrypted and masked).
    """

    class Kind(models.TextChoices):
        ABHA_NUMBER = "abha_number", "ABHA number"
        ABHA_ADDRESS = "abha_address", "ABHA address"
        AADHAAR = "aadhaar", "Aadhaar number"
        PASSPORT = "passport", "Passport"
        VOTER_ID = "voter_id", "Voter ID (EPIC)"
        DRIVING_LICENCE = "driving_licence", "Driving licence"
        SSN = "ssn", "Social Security number"
        PREVIOUS_MRN = "previous_mrn", "Previous hospital's MRN"

    class Verification(models.TextChoices):
        UNVERIFIED = "unverified", "Not verified"
        VERIFIED = "verified", "Verified"

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="identifiers")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    value_encrypted = models.TextField(help_text="The full number, encrypted; never shown")
    value_hash = models.CharField(
        max_length=64, help_text="Keyed fingerprint of the number, to find it and refuse duplicates"
    )
    value_display = models.CharField(max_length=40, help_text="Masked, e.g. XXXX XXXX 1234")
    issuer = models.CharField(
        max_length=100, blank=True, help_text="e.g. the issuing country or state, or hospital"
    )
    verification = models.CharField(
        max_length=16,
        choices=Verification.choices,
        default=Verification.UNVERIFIED,
        editable=False,
        help_text="Checking with UIDAI / ABDM comes later; typed numbers are not verified",
    )
    valid_until = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, editable=False)
    ended_at = models.DateTimeField(null=True, blank=True, editable=False)
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    end_reason = models.CharField(max_length=255, blank=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "patient_identifiers"
        ordering = ["-is_active", "kind", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "kind", "value_hash"],
                condition=Q(is_active=True, kind__in=UNIQUE_IDENTIFIER_KINDS),
                name="patient_identifiers_unique_number",
                violation_error_message="This number is already recorded for another patient.",
            )
        ]
        indexes = [models.Index(fields=["value_hash"], name="patient_identifiers_hash_idx")]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.value_display}"


class PatientConsent(OrganizationOwnedModel):
    """A consent decision: a new row for every change, so the history stays (D9).

    The latest row of a kind is the current decision. Append-only (database trigger).
    """

    class Kind(models.TextChoices):
        PRIVACY_NOTICE = "privacy_notice", "Privacy notice given; agrees to processing for care"
        SMS = "sms", "Messages by SMS"
        EMAIL = "email", "Messages by email"

    class Status(models.TextChoices):
        GIVEN = "given", "Given"
        REFUSED = "refused", "Refused"
        WITHDRAWN = "withdrawn", "Withdrawn"

    class Method(models.TextChoices):
        VERBAL = "verbal", "Told the front desk"
        SIGNED_FORM = "signed_form", "Signed a form"

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="consents")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(max_length=16, choices=Status.choices)
    method = models.CharField(max_length=16, choices=Method.choices, default=Method.VERBAL)
    note = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "patient_consents"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["patient", "kind", "-created_at"], name="patient_consents_idx")
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.get_status_display()}"


class IdentifierHashKey(UUIDPrimaryKeyModel):
    """The hospital's random key for ID-number fingerprints, stored encrypted (one row).

    A plain hash of a 12-digit number could be reversed by trying every number; a keyed one
    cannot without this key. It never changes (fingerprints must stay comparable); its
    encryption follows the field-encryption keys and their rotation.
    """

    key_encrypted = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "patient_identifier_keys"

    def __str__(self) -> str:
        return "ID number fingerprint key"
