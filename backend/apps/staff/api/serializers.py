from datetime import timedelta

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.facilities.models import Department

from ..models import (
    Designation,
    QualificationType,
    Specialty,
    StaffCredential,
    StaffDepartmentAssignment,
    StaffDocument,
    StaffMember,
    StaffQualification,
)

CATALOG_FIELDS = ["is_active", "is_custom", "version"]


class SpecialtySerializer(serializers.ModelSerializer):
    class Meta:
        model = Specialty
        fields = ["id", "code", "name", *CATALOG_FIELDS]
        read_only_fields = fields


class QualificationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = QualificationType
        fields = ["id", "code", "name", "category", "country", *CATALOG_FIELDS]
        read_only_fields = fields


class DesignationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Designation
        fields = [
            "id",
            "code",
            "name",
            "category",
            "country",
            "seniority",
            "description",
            *CATALOG_FIELDS,
        ]
        read_only_fields = fields


# Add / change catalog entries (HIMS-STAFF-010). Codes are created automatically and never change.


class SpecialtyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)


class SpecialtyUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=255, required=False)
    is_active = serializers.BooleanField(required=False)


class QualificationTypeCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    category = serializers.ChoiceField(QualificationType.Category.choices)
    country = serializers.RegexField(
        r"^(IN|US)?$",
        max_length=2,
        required=False,
        allow_blank=True,
        help_text="IN, US, or blank for both countries",
    )


class QualificationTypeUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=255, required=False)
    category = serializers.ChoiceField(QualificationType.Category.choices, required=False)
    country = serializers.RegexField(
        r"^(IN|US)?$",
        max_length=2,
        required=False,
        allow_blank=True,
        help_text="IN, US, or blank for both countries",
    )
    is_active = serializers.BooleanField(required=False)


class DesignationCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    category = serializers.ChoiceField(Designation.Category.choices)
    country = serializers.RegexField(
        r"^(IN|US)?$",
        max_length=2,
        required=False,
        allow_blank=True,
        help_text="IN, US, or blank for both countries",
    )
    seniority = serializers.IntegerField(min_value=1, max_value=10)
    description = serializers.CharField(required=False, allow_blank=True, default="")


class DesignationUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=255, required=False)
    category = serializers.ChoiceField(Designation.Category.choices, required=False)
    country = serializers.RegexField(
        r"^(IN|US)?$",
        max_length=2,
        required=False,
        allow_blank=True,
        help_text="IN, US, or blank for both countries",
    )
    seniority = serializers.IntegerField(min_value=1, max_value=10, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)


class StaffDepartmentAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffDepartmentAssignment
        fields = [
            "id",
            "department",
            "designation",
            "designation_name",
            "specialty",
            "is_primary",
            "valid_from",
            "valid_until",
            "department_name",
            "facility_name",
            "specialty_name",
            "is_current",
        ]
        read_only_fields = ["id"]

    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.all())
    designation = serializers.PrimaryKeyRelatedField(
        queryset=Designation.objects.filter(is_active=True)
    )
    designation_name = serializers.CharField(source="designation.name", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    facility_name = serializers.CharField(source="department.facility.name", read_only=True)
    specialty_name = serializers.CharField(
        source="specialty.name", read_only=True, default=None, allow_null=True
    )
    is_current = serializers.SerializerMethodField()

    def get_is_current(self, assignment) -> bool:
        today = timezone.localdate()
        return assignment.valid_from <= today and (
            assignment.valid_until is None or assignment.valid_until >= today
        )

    specialty = serializers.PrimaryKeyRelatedField(
        queryset=Specialty.objects.filter(is_active=True), required=False, allow_null=True
    )


class StaffQualificationSerializer(serializers.ModelSerializer):
    qualification_type = serializers.PrimaryKeyRelatedField(
        queryset=QualificationType.objects.filter(is_active=True)
    )
    specialty = serializers.PrimaryKeyRelatedField(
        queryset=Specialty.objects.filter(is_active=True), required=False, allow_null=True
    )

    class Meta:
        model = StaffQualification
        fields = [
            "id",
            "qualification_type",
            "specialty",
            "institution",
            "year_awarded",
            "verification_status",
            "verified_by",
            "verified_by_name",
            "verified_at",
            "qualification_type_name",
            "specialty_name",
        ]
        read_only_fields = ["id", "verification_status", "verified_by", "verified_at"]

    qualification_type_name = serializers.CharField(
        source="qualification_type.name", read_only=True
    )
    specialty_name = serializers.CharField(
        source="specialty.name", read_only=True, default=None, allow_null=True
    )
    verified_by_name = serializers.CharField(
        source="verified_by.display_name", read_only=True, default=None, allow_null=True
    )


# A credential within this many days of expiry is shown as "expiring soon".
EXPIRY_WARNING_DAYS = 60


class StaffCredentialSerializer(serializers.ModelSerializer):
    credential_type_label = serializers.CharField(
        source="get_credential_type_display", read_only=True
    )
    verified_by_name = serializers.CharField(
        source="verified_by.display_name", read_only=True, default=None, allow_null=True
    )
    expiry_state = serializers.SerializerMethodField(
        help_text="no_expiry, valid, expiring_soon (within 60 days) or expired"
    )

    def get_expiry_state(self, credential) -> str:
        if credential.expires_at is None:
            return "no_expiry"
        today = timezone.localdate()
        if credential.expires_at < today:
            return "expired"
        if credential.expires_at <= today + timedelta(days=EXPIRY_WARNING_DAYS):
            return "expiring_soon"
        return "valid"

    class Meta:
        model = StaffCredential
        fields = [
            "id",
            "credential_type",
            "registration_number",
            "issuing_authority",
            "jurisdiction",
            "valid_from",
            "expires_at",
            "verification_status",
            "verified_by",
            "verified_by_name",
            "verified_at",
            "credential_type_label",
            "expiry_state",
        ]
        read_only_fields = ["id", "verification_status", "verified_by", "verified_at"]
        validators = []


class StaffMemberSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True, allow_null=True)
    staff_type_label = serializers.CharField(source="get_staff_type_display", read_only=True)
    employment_status_label = serializers.CharField(
        source="get_employment_status_display", read_only=True
    )

    class Meta:
        model = StaffMember
        fields = [
            "id",
            "user",
            "email",
            "employee_number",
            "given_name",
            "family_name",
            "staff_type",
            "staff_type_label",
            "employment_status",
            "employment_status_label",
            "joined_on",
            "left_on",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class StaffDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(
        source="uploaded_by.display_name", read_only=True, default=None, allow_null=True
    )
    is_archived = serializers.SerializerMethodField()

    def get_is_archived(self, document) -> bool:
        return document.archived_at is not None

    class Meta:
        model = StaffDocument
        fields = [
            "id",
            "staff",
            "credential",
            "qualification",
            "original_name",
            "content_type",
            "size_bytes",
            "uploaded_by_name",
            "created_at",
            "is_archived",
            "archived_at",
            "archive_reason",
        ]
        read_only_fields = fields


class StaffAccountSerializer(serializers.Serializer):
    """The person's sign-in account, so HR can see whether they can log in yet."""

    has_login = serializers.BooleanField()
    email = serializers.EmailField(allow_null=True)
    is_active = serializers.BooleanField(help_text="False = cannot sign in (e.g. terminated).")
    activated = serializers.BooleanField(help_text="The person has chosen a password.")
    invitation_expires_at = serializers.DateTimeField(
        allow_null=True, help_text="An open invitation link and when it stops working."
    )
    two_factor_enabled = serializers.BooleanField()


class StaffMemberDetailSerializer(StaffMemberSerializer):
    department_assignments = StaffDepartmentAssignmentSerializer(many=True, read_only=True)
    qualifications = StaffQualificationSerializer(many=True, read_only=True)
    credentials = StaffCredentialSerializer(many=True, read_only=True)
    documents = serializers.SerializerMethodField(
        help_text="Licence and qualification documents, newest first (archived ones included)."
    )
    account = serializers.SerializerMethodField()

    class Meta(StaffMemberSerializer.Meta):
        fields = [
            *StaffMemberSerializer.Meta.fields,
            "account",
            "department_assignments",
            "qualifications",
            "credentials",
            "documents",
        ]
        read_only_fields = fields

    @extend_schema_field(StaffDocumentSerializer(many=True))
    def get_documents(self, staff) -> list:
        return StaffDocumentSerializer(staff.documents.all(), many=True).data

    @extend_schema_field(StaffAccountSerializer)
    def get_account(self, staff) -> dict:
        from apps.identity.mfa import confirmed_device
        from apps.identity.models import Invitation

        user = staff.user
        if user is None:
            data = {
                "has_login": False,
                "email": None,
                "is_active": False,
                "activated": False,
                "invitation_expires_at": None,
                "two_factor_enabled": False,
            }
        else:
            invitation = (
                Invitation.objects.filter(
                    user=user,
                    accepted_at__isnull=True,
                    revoked_at__isnull=True,
                    expires_at__gt=timezone.now(),
                )
                .order_by("-created_at")
                .first()
            )
            data = {
                "has_login": True,
                "email": user.email,
                "is_active": user.is_active,
                "activated": user.has_usable_password(),
                "invitation_expires_at": invitation.expires_at if invitation else None,
                "two_factor_enabled": confirmed_device(user) is not None,
            }
        return StaffAccountSerializer(data).data


class StaffMemberCreateSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        required=False, allow_null=True, help_text="Creates a login identity (invitation pending)."
    )

    class Meta:
        model = StaffMember
        fields = [
            "email",
            "employee_number",
            "given_name",
            "family_name",
            "staff_type",
            "joined_on",
        ]
        validators = []


class StaffMemberUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    given_name = serializers.CharField(max_length=150, required=False)
    family_name = serializers.CharField(max_length=150, required=False)
    staff_type = serializers.ChoiceField(StaffMember.StaffType.choices, required=False)
    employment_status = serializers.ChoiceField(
        StaffMember.EmploymentStatus.choices, required=False
    )
    left_on = serializers.DateField(required=False, allow_null=True)


class CredentialVerificationSerializer(serializers.Serializer):
    verified = serializers.BooleanField()
    reason = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class EndAssignmentSerializer(serializers.Serializer):
    valid_until = serializers.DateField(
        required=False, allow_null=True, help_text="Last day of the posting (default: today)."
    )
    reason = serializers.CharField(max_length=2000)


class InvitationSentSerializer(serializers.Serializer):
    email = serializers.EmailField()
    expires_at = serializers.DateTimeField()


# --- Documents and licence expiry (HIMS-STAFF-005/006) ---------------------------------------


class StaffDocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="PDF, JPG or PNG, up to 10 MB")
    credential = serializers.UUIDField(required=False, allow_null=True)
    qualification = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, data):
        if bool(data.get("credential")) == bool(data.get("qualification")):
            raise serializers.ValidationError(
                "Choose the licence or the qualification this document belongs to."
            )
        return data


class ArchiveSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class ExpiringCredentialSerializer(StaffCredentialSerializer):
    staff_member_id = serializers.UUIDField(source="staff_id", read_only=True)
    staff_name = serializers.SerializerMethodField()
    employee_number = serializers.CharField(source="staff.employee_number", read_only=True)
    staff_type_label = serializers.CharField(source="staff.get_staff_type_display", read_only=True)
    days_left = serializers.SerializerMethodField(help_text="Negative = days since it expired")
    last_alert = serializers.SerializerMethodField(
        help_text="Last alert sent: 'expired', 'N days before' or null"
    )
    last_alert_at = serializers.SerializerMethodField()

    class Meta(StaffCredentialSerializer.Meta):
        fields = [
            *StaffCredentialSerializer.Meta.fields,
            "staff_member_id",
            "staff_name",
            "employee_number",
            "staff_type_label",
            "days_left",
            "last_alert",
            "last_alert_at",
        ]
        read_only_fields = fields

    def get_staff_name(self, credential) -> str:
        return f"{credential.staff.given_name} {credential.staff.family_name}"

    def get_days_left(self, credential) -> int:
        return (credential.expires_at - timezone.localdate()).days

    def _alert(self, credential):
        alerts = [
            a for a in credential.expiry_alerts.all() if a.expires_at == credential.expires_at
        ]
        return max(alerts, key=lambda a: a.sent_at) if alerts else None

    def get_last_alert(self, credential) -> str | None:
        alert = self._alert(credential)
        if alert is None:
            return None
        return "expired" if alert.days_before == 0 else f"{alert.days_before} days before"

    def get_last_alert_at(self, credential) -> str | None:
        alert = self._alert(credential)
        return alert.sent_at.isoformat() if alert else None
