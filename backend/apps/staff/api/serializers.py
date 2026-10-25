from rest_framework import serializers

from apps.facilities.models import Department

from ..models import (
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


class StaffDepartmentAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffDepartmentAssignment
        fields = [
            "id",
            "department",
            "designation",
            "specialty",
            "is_primary",
            "valid_from",
            "valid_until",
        ]
        read_only_fields = ["id"]

    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.all())
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
            "verified_at",
        ]
        read_only_fields = ["id", "verification_status", "verified_by", "verified_at"]


class StaffCredentialSerializer(serializers.ModelSerializer):
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
            "verified_at",
        ]
        read_only_fields = ["id", "verification_status", "verified_by", "verified_at"]
        validators = []


class StaffMemberSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True, allow_null=True)

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
            "employment_status",
            "joined_on",
            "left_on",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class StaffMemberDetailSerializer(StaffMemberSerializer):
    department_assignments = StaffDepartmentAssignmentSerializer(many=True, read_only=True)
    qualifications = StaffQualificationSerializer(many=True, read_only=True)
    credentials = StaffCredentialSerializer(many=True, read_only=True)

    class Meta(StaffMemberSerializer.Meta):
        fields = [
            *StaffMemberSerializer.Meta.fields,
            "department_assignments",
            "qualifications",
            "credentials",
        ]
        read_only_fields = fields


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
