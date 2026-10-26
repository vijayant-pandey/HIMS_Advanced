"""Staff, qualifications and credentials (spec 4.3, 9.4).

Academic qualification, professional registration, designation, specialty and clinical
privilege are separate concepts and are modelled separately.
"""

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from common.models import (
    OrganizationOwnedModel,
    TimeStampedModel,
    UUIDPrimaryKeyModel,
    VersionedModel,
)


class VerificationStatus(models.TextChoices):
    UNVERIFIED = "unverified", "Unverified"
    VERIFIED = "verified", "Verified"
    REJECTED = "rejected", "Rejected"


class Specialty(UUIDPrimaryKeyModel, TimeStampedModel):
    """Controlled specialty catalog. Owned by clinical informatics."""

    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "specialties"
        ordering = ["name"]
        verbose_name_plural = "specialties"

    def __str__(self) -> str:
        return self.name


class QualificationType(UUIDPrimaryKeyModel, TimeStampedModel):
    """Controlled qualification catalog (MBBS, MD, DNB, RN...). Country-specific where needed."""

    class Category(models.TextChoices):
        DEGREE = "degree", "Degree"
        DIPLOMA = "diploma", "Diploma"
        FELLOWSHIP = "fellowship", "Fellowship"
        CERTIFICATION = "certification", "Certification"

    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=32, choices=Category.choices)
    country = models.CharField(max_length=2, blank=True, help_text="Blank when not country-bound")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "qualification_types"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Designation(UUIDPrimaryKeyModel, TimeStampedModel):
    """Controlled designation catalog: job titles on a junior-to-senior ladder (HIMS-STAFF-009).

    A designation is a job title, not a permission: what someone may do comes from role
    assignments (docs/status/Hospital_Departments_and_Doctors_RBAC.MD). ``seniority`` runs from
    1 (entry level) to 10 (organization leadership) and is comparable within a category.
    """

    class Category(models.TextChoices):
        MEDICAL = "medical", "Medical (doctors)"
        NURSING = "nursing", "Nursing"
        PHARMACY = "pharmacy", "Pharmacy"
        ALLIED_HEALTH = "allied_health", "Allied health & technicians"
        ADMINISTRATION = "administration", "Administration & management"
        SUPPORT = "support", "Support services"
        OTHER = "other", "Other"

    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=32, choices=Category.choices)
    country = models.CharField(max_length=2, blank=True, help_text="Blank when used in both")
    seniority = models.PositiveSmallIntegerField(help_text="1 = entry level ... 10 = leadership")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "designations"
        ordering = ["category", "seniority", "name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(seniority__gte=1) & Q(seniority__lte=10),
                name="designation_seniority_range",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.country})" if self.country else self.name


class StaffMember(OrganizationOwnedModel, VersionedModel):
    class StaffType(models.TextChoices):
        DOCTOR = "doctor", "Doctor"
        NURSE = "nurse", "Nurse"
        PHARMACIST = "pharmacist", "Pharmacist"
        LAB_TECHNICIAN = "lab_technician", "Laboratory technician"
        RADIOLOGIST = "radiologist", "Radiologist"
        DIETITIAN = "dietitian", "Dietitian"
        ADMINISTRATOR = "administrator", "Administrator"
        SUPPORT = "support", "Support staff"

    class EmploymentStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_LEAVE = "on_leave", "On leave"
        SUSPENDED = "suspended", "Suspended"
        TERMINATED = "terminated", "Terminated"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="staff_member",
    )
    employee_number = models.CharField(max_length=64)
    given_name = models.CharField(max_length=150)
    family_name = models.CharField(max_length=150)
    staff_type = models.CharField(max_length=32, choices=StaffType.choices)
    employment_status = models.CharField(
        max_length=16, choices=EmploymentStatus.choices, default=EmploymentStatus.ACTIVE
    )
    joined_on = models.DateField()
    left_on = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "staff_members"
        ordering = ["family_name", "given_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "employee_number"], name="staff_employee_number_unique"
            ),
            models.CheckConstraint(
                condition=Q(left_on__isnull=True) | Q(left_on__gte=F("joined_on")),
                name="staff_left_after_joined",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.given_name} {self.family_name}"


class StaffDepartmentAssignment(OrganizationOwnedModel):
    staff = models.ForeignKey(
        StaffMember, on_delete=models.PROTECT, related_name="department_assignments"
    )
    department = models.ForeignKey(
        "facilities.Department", on_delete=models.PROTECT, related_name="staff_assignments"
    )
    designation = models.ForeignKey(Designation, on_delete=models.PROTECT, related_name="+")
    specialty = models.ForeignKey(
        Specialty, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    is_primary = models.BooleanField(default=False)
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "staff_department_assignments"
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True) | Q(valid_until__gte=F("valid_from")),
                name="staff_assignment_valid_range",
            )
        ]


class StaffQualification(OrganizationOwnedModel):
    staff = models.ForeignKey(StaffMember, on_delete=models.PROTECT, related_name="qualifications")
    qualification_type = models.ForeignKey(
        QualificationType, on_delete=models.PROTECT, related_name="+"
    )
    specialty = models.ForeignKey(
        Specialty, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    institution = models.CharField(max_length=255)
    year_awarded = models.PositiveSmallIntegerField()
    verification_status = models.CharField(
        max_length=16, choices=VerificationStatus.choices, default=VerificationStatus.UNVERIFIED
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "staff_qualifications"
        constraints = [
            models.CheckConstraint(
                condition=Q(year_awarded__gte=1900), name="staff_qualification_year_sane"
            )
        ]


class StaffCredential(OrganizationOwnedModel):
    """Professional registration/licence. Verification and expiry are independent of whether
    the person can sign in (spec 28.3)."""

    class CredentialType(models.TextChoices):
        MEDICAL_REGISTRATION = "medical_registration", "Medical council registration"
        NURSING_REGISTRATION = "nursing_registration", "Nursing council registration"
        PHARMACY_REGISTRATION = "pharmacy_registration", "Pharmacy council registration"
        STATE_LICENSE = "state_license", "State licence (US)"
        NPI = "npi", "National Provider Identifier (US)"
        DEA_REGISTRATION = "dea_registration", "DEA registration (US)"
        OTHER = "other", "Other"

    staff = models.ForeignKey(StaffMember, on_delete=models.PROTECT, related_name="credentials")
    credential_type = models.CharField(max_length=32, choices=CredentialType.choices)
    registration_number = models.CharField(max_length=64)
    issuing_authority = models.CharField(max_length=255)
    jurisdiction = models.CharField(max_length=16, help_text="ISO 3166-2, e.g. IN-KA or US-CA")
    valid_from = models.DateField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True)
    verification_status = models.CharField(
        max_length=16, choices=VerificationStatus.choices, default=VerificationStatus.UNVERIFIED
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "staff_credentials"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "organization",
                    "credential_type",
                    "issuing_authority",
                    "registration_number",
                ],
                name="staff_credential_unique",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__isnull=True)
                | Q(valid_from__isnull=True)
                | Q(expires_at__gt=F("valid_from")),
                name="staff_credential_valid_range",
            ),
        ]
        indexes = [models.Index(fields=["expires_at"], name="staff_credential_expiry_idx")]
