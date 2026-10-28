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
    StaffMember,
    StaffQualification,
)


class SpecialtySerializer(serializers.ModelSerializer):
    class Meta:
        model = Specialty
        fields = ["id", "code", "name"]
        read_only_fields = fields


class QualificationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = QualificationType
        fields = ["id", "code", "name", "category", "country"]
        read_only_fields = fields


class DesignationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Designation
        fields = ["id", "code", "name", "category", "country", "seniority"]
        read_only_fields = fields


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
    account = serializers.SerializerMethodField()

    class Meta(StaffMemberSerializer.Meta):
        fields = [
            *StaffMemberSerializer.Meta.fields,
            "account",
            "department_assignments",
            "qualifications",
            "credentials",
        ]
        read_only_fields = fields

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
