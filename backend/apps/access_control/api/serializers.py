from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.facilities.models import Department, Facility

from ..catalog import PERMISSIONS
from ..models import (
    AccessDelegation,
    AccessReview,
    AccessReviewItem,
    Permission,
    Role,
    RoleAssignment,
)


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
    covering_for_name = serializers.CharField(
        source="delegation.delegator.display_name",
        read_only=True,
        default=None,
        allow_null=True,
        help_text="Set when this access is lent for cover (HIMS-IAM-017): whose access it is.",
    )

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
            "delegation",
            "covering_for_name",
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


# --- Access reviews (HIMS-IAM-012) ------------------------------------------------------------


class AccessReviewSummarySerializer(serializers.Serializer):
    pending = serializers.IntegerField()
    keep = serializers.IntegerField()
    remove = serializers.IntegerField()
    ended = serializers.IntegerField()


class AccessReviewSerializer(serializers.ModelSerializer):
    started_by_name = serializers.CharField(
        source="started_by.display_name", read_only=True, default=None, allow_null=True
    )
    completed_by_name = serializers.CharField(
        source="completed_by.display_name", read_only=True, default=None, allow_null=True
    )
    summary = serializers.SerializerMethodField()

    def get_summary(self, review) -> AccessReviewSummarySerializer:
        from ..reviews import summary

        return summary(review)

    class Meta:
        model = AccessReview
        fields = [
            "id",
            "title",
            "status",
            "due_on",
            "created_at",
            "started_by_name",
            "completed_at",
            "completed_by_name",
            "notes",
            "summary",
            "version",
        ]
        read_only_fields = fields


class AccessReviewItemSerializer(serializers.ModelSerializer):
    decided_by_name = serializers.CharField(
        source="decided_by.display_name", read_only=True, default=None, allow_null=True
    )
    is_own = serializers.SerializerMethodField(
        help_text="Your own access: someone else must decide it."
    )

    def get_is_own(self, item) -> bool:
        request = self.context.get("request")
        return bool(request and item.assignment.user_id == request.user.pk)

    class Meta:
        model = AccessReviewItem
        fields = [
            "id",
            "person_name",
            "person_email",
            "account_active",
            "last_signed_in_at",
            "role_name",
            "scope",
            "granted_at",
            "access_ends_at",
            "decision",
            "decided_by_name",
            "decided_at",
            "comment",
            "is_own",
        ]
        read_only_fields = fields


class AccessReviewStartSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    due_on = serializers.DateField(
        required=False, allow_null=True, default=None, help_text="Finish by (default 14 days)."
    )


class AccessReviewDecideSerializer(serializers.Serializer):
    items = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=500)
    decision = serializers.ChoiceField(
        choices=[AccessReviewItem.Decision.KEEP, AccessReviewItem.Decision.REMOVE]
    )
    comment = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class AccessReviewCompleteSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    notes = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")


class AccessReviewCancelSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    reason = serializers.CharField(max_length=2000)


class AccessReviewScheduleSerializer(serializers.Serializer):
    interval_days = serializers.IntegerField()
    last_completed_at = serializers.DateTimeField(allow_null=True)
    next_due_on = serializers.DateField()
    review_due = serializers.BooleanField(help_text="No review in progress and one is due.")
    open_review_id = serializers.UUIDField(allow_null=True)
    open_review_overdue = serializers.BooleanField()


# --- Cover arrangements / delegated access (HIMS-IAM-017) -------------------------------------


class PersonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    display_name = serializers.CharField()
    email = serializers.EmailField()


class LentAccessSerializer(serializers.ModelSerializer):
    """One copy of the covered person's access lent to the covering person."""

    role_name = serializers.CharField(source="role.name", read_only=True)
    scope = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField(help_text="Usable right now.")

    def get_scope(self, assignment) -> str:
        from ..reviews import scope_label

        return scope_label(assignment)

    def get_is_active(self, assignment) -> bool:
        return RoleAssignmentSerializer().get_is_active(assignment)

    class Meta:
        model = RoleAssignment
        fields = [
            "id",
            "role_name",
            "scope",
            "valid_from",
            "valid_until",
            "revoked_at",
            "revocation_reason",
            "is_active",
        ]
        read_only_fields = fields


class AccessDelegationSerializer(serializers.ModelSerializer):
    delegator = PersonSerializer(read_only=True)
    delegate = PersonSerializer(read_only=True)
    status = serializers.ChoiceField(choices=AccessDelegation.Status.choices, read_only=True)
    status_label = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(
        source="created_by.display_name", read_only=True, default=None, allow_null=True
    )
    ended_by_name = serializers.CharField(
        source="ended_by.display_name", read_only=True, default=None, allow_null=True
    )
    lent_access = LentAccessSerializer(source="assignments", many=True, read_only=True)

    def get_status_label(self, delegation) -> str:
        return AccessDelegation.Status(delegation.status).label

    class Meta:
        model = AccessDelegation
        fields = [
            "id",
            "delegator",
            "delegate",
            "starts_at",
            "ends_at",
            "reason",
            "status",
            "status_label",
            "created_by_name",
            "created_at",
            "ended_at",
            "ended_by_name",
            "end_reason",
            "lent_access",
            "version",
        ]
        read_only_fields = fields


class SkippedAccessSerializer(serializers.Serializer):
    role_name = serializers.CharField()
    scope = serializers.CharField()
    why = serializers.CharField()


class AccessDelegationCreatedSerializer(AccessDelegationSerializer):
    skipped = SkippedAccessSerializer(many=True, read_only=True, default=list)

    class Meta(AccessDelegationSerializer.Meta):
        fields = [*AccessDelegationSerializer.Meta.fields, "skipped"]
        read_only_fields = fields


class AccessDelegationCreateSerializer(serializers.Serializer):
    delegator = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(), help_text="The person being covered."
    )
    delegate = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(), help_text="The person covering."
    )
    starts_at = serializers.DateTimeField(
        required=False, allow_null=True, default=None, help_text="Empty = now."
    )
    ends_at = serializers.DateTimeField()
    reason = serializers.CharField(max_length=2000)
    assignments = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_null=True,
        default=None,
        help_text="Which of the covered person's access to lend. Empty = all that can be lent.",
    )


class AccessDelegationEndSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=2000)


class DelegableAccessSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    role_name = serializers.CharField()
    scope = serializers.CharField()
    valid_until = serializers.DateTimeField(allow_null=True)
    can_lend = serializers.BooleanField()
    why_not = serializers.CharField(allow_blank=True)
