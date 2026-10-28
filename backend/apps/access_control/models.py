from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from common.models import OrganizationOwnedModel, UUIDPrimaryKeyModel, VersionedModel


class Permission(UUIDPrimaryKeyModel):
    """A permission codename, synchronised from ``catalog.PERMISSIONS``."""

    codename = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "permissions"
        ordering = ["codename"]

    def __str__(self) -> str:
        return self.codename


class Role(OrganizationOwnedModel, VersionedModel):
    code = models.SlugField(max_length=64)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False)
    permissions = models.ManyToManyField(Permission, through="RolePermission", related_name="roles")

    class Meta:
        db_table = "roles"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="roles_code_unique")
        ]

    def __str__(self) -> str:
        return self.name


class RolePermission(UUIDPrimaryKeyModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "role_permissions"
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="role_permission_unique")
        ]


class RoleAssignment(OrganizationOwnedModel):
    """Grants a role to a user, organization-wide or limited to a facility/department.

    Assignments are time-bounded and revoked rather than deleted, preserving access history
    for audit and periodic access reviews (spec 4.4, 13.2).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="role_assignments"
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="assignments")
    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    department = models.ForeignKey(
        "facilities.Department", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(blank=True)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    revocation_reason = models.TextField(blank=True)

    class Meta:
        db_table = "role_assignments"
        constraints = [
            models.CheckConstraint(
                condition=Q(department__isnull=True) | Q(facility__isnull=False),
                name="role_assignment_department_needs_facility",
            ),
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True) | Q(valid_until__gt=models.F("valid_from")),
                name="role_assignment_valid_range",
            ),
            models.UniqueConstraint(
                fields=["user", "role", "facility", "department"],
                condition=Q(revoked_at__isnull=True),
                nulls_distinct=False,
                name="role_assignment_active_unique",
            ),
        ]
        indexes = [models.Index(fields=["user", "revoked_at"], name="role_assignment_user_idx")]
