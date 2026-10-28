from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.facilities.models import Department, Facility

from ..catalog import PERMISSIONS
from ..models import Permission, Role, RoleAssignment


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["codename", "description"]
        read_only_fields = fields


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SlugRelatedField(many=True, read_only=True, slug_field="codename")
    active_assignments = serializers.IntegerField(
        read_only=True, default=0, help_text="People who hold this role now."
    )

    class Meta:
        model = Role
        fields = [
            "id",
            "code",
            "name",
            "description",
            "is_system",
            "permissions",
            "active_assignments",
            "version",
            "created_at",
        ]
        read_only_fields = fields


class RoleUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=128, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    permissions = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(PERMISSIONS)),
        allow_empty=False,
        required=False,
    )


class RoleCreateSerializer(serializers.Serializer):
    code = serializers.SlugField(max_length=64)
    name = serializers.CharField(max_length=128)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    permissions = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(PERMISSIONS)), allow_empty=False
    )


class RoleAssignmentSerializer(serializers.ModelSerializer):
    role_code = serializers.CharField(source="role.code", read_only=True)
    role_name = serializers.CharField(source="role.name", read_only=True)
    user_display_name = serializers.CharField(source="user.display_name", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    facility_name = serializers.CharField(
        source="facility.name", read_only=True, default=None, allow_null=True
    )
    department_name = serializers.CharField(
        source="department.name", read_only=True, default=None, allow_null=True
    )
    granted_by_name = serializers.CharField(
        source="granted_by.display_name", read_only=True, default=None, allow_null=True
    )
    revoked_by_name = serializers.CharField(
        source="revoked_by.display_name", read_only=True, default=None, allow_null=True
    )
    is_active = serializers.SerializerMethodField(help_text="Not revoked and not expired.")

    def get_is_active(self, assignment) -> bool:
        from django.utils import timezone

        now = timezone.now()
        return (
            assignment.revoked_at is None
            and assignment.valid_from <= now
            and (assignment.valid_until is None or assignment.valid_until > now)
        )

    class Meta:
        model = RoleAssignment
        fields = [
            "id",
            "user",
            "role",
            "role_code",
            "role_name",
            "user_display_name",
            "user_email",
            "facility_name",
            "department_name",
            "granted_by_name",
            "revoked_by_name",
            "is_active",
            "facility",
            "department",
            "valid_from",
            "valid_until",
            "reason",
            "granted_by",
            "revoked_at",
            "revoked_by",
            "revocation_reason",
            "created_at",
        ]
        read_only_fields = fields


class RoleAssignmentCreateSerializer(serializers.Serializer):
    user = serializers.PrimaryKeyRelatedField(queryset=get_user_model().objects.all())
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all())
    facility = serializers.PrimaryKeyRelatedField(
        queryset=Facility.objects.all(), required=False, allow_null=True, default=None
    )
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True, default=None
    )
    valid_until = serializers.DateTimeField(required=False, allow_null=True, default=None)
    reason = serializers.CharField(max_length=2000)


class RevokeSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=2000)
