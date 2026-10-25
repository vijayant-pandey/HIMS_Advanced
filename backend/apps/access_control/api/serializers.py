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

    class Meta:
        model = Role
        fields = ["id", "code", "name", "description", "is_system", "permissions", "created_at"]
        read_only_fields = fields


class RoleCreateSerializer(serializers.Serializer):
    code = serializers.SlugField(max_length=64)
    name = serializers.CharField(max_length=128)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    permissions = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(PERMISSIONS)), allow_empty=False
    )


class RoleAssignmentSerializer(serializers.ModelSerializer):
    role_code = serializers.CharField(source="role.code", read_only=True)

    class Meta:
        model = RoleAssignment
        fields = [
            "id",
            "user",
            "role",
            "role_code",
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
