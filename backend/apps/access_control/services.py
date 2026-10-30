from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditAction, record_audit_event
from apps.facilities.models import Department, Facility
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError, ScopeViolation

from .catalog import PERMISSIONS, SYSTEM_ROLES
from .models import Permission, Role, RoleAssignment
from .selectors import clear_permission_cache, has_permission


def sync_permission_catalog() -> None:
    """Make the permissions table match the catalog. Removed codenames are deactivated, never
    deleted, so historical role definitions stay interpretable."""
    for codename, description in PERMISSIONS.items():
        Permission.objects.update_or_create(
            codename=codename, defaults={"description": description, "is_active": True}
        )
    Permission.objects.exclude(codename__in=PERMISSIONS).update(is_active=False)


def _require_grantable(actor, permission_codenames, *, facility_id=None, department_id=None):
    """Prevent privilege escalation: an actor can only hand out permissions they hold
    themselves at the target scope."""
    if actor is None:
        return  # provisioning/system context
    missing = [
        code
        for code in permission_codenames
        if not has_permission(actor, code, facility_id=facility_id, department_id=department_id)
    ]
    if missing:
        raise ScopeViolation("You cannot grant permissions you do not hold for this scope.")


@transaction.atomic
def create_role(*, actor, organization, code, name, description="", permissions=(), request=None):
    unknown = [p for p in permissions if p not in PERMISSIONS]
    if unknown:
        raise ConflictError(f"Unknown permissions: {', '.join(sorted(unknown))}")
    _require_grantable(actor, permissions)
    if Role.objects.filter(organization=organization, code=code).exists():
        raise ConflictError("A role with this code already exists.", code="DUPLICATE_CODE")
    role = Role.objects.create(
        organization=organization, code=code, name=name, description=description
    )
    role.permissions.set(Permission.objects.filter(codename__in=permissions))
    record_audit_event(
        action=AuditAction.ROLE_CREATED,
        resource_type="role",
        resource_id=role.pk,
        actor=actor,
        request=request,
        changes={"after": {"code": code, "name": name, "permissions": sorted(permissions)}},
    )
    return role


@transaction.atomic
def create_system_roles(organization) -> dict[str, Role]:
    """Create any missing system roles (idempotent). A role code an organization already uses
    for its own custom role is left untouched."""
    roles = {}
    for code, definition in SYSTEM_ROLES.items():
        existing = Role.objects.filter(organization=organization, code=code).first()
        if existing is not None:
            roles[code] = existing
            continue
        role = create_role(
            actor=None,
            organization=organization,
            code=code,
            name=definition["name"],
            description=definition["description"],
            permissions=definition["permissions"],
        )
        role.is_system = True
        role.save(update_fields=["is_system"])
        roles[code] = role
    return roles


def validate_role_assignment(
    *, actor, user, role: Role, facility=None, department=None, valid_until=None
) -> Facility | None:
    """All rules for granting a role (also used by the admin console form). Returns the
    effective facility (derived from the department when omitted)."""
    if actor is not None and user.pk == actor.pk:
        # Separation of duties (spec 13.2): e.g. temporary access must not be extended by its
        # holder. Another administrator has to grant it.
        raise ConflictError(
            "You cannot give yourself access; ask another administrator.", code="SELF_ASSIGNMENT"
        )
    if department is not None:
        if facility is None:
            facility = department.facility
        if department.facility_id != facility.pk:
            raise ConflictError("The department does not belong to the selected facility.")
    if facility is not None and facility.status != Facility.Status.ACTIVE:
        raise ConflictError("Roles can only be granted at an active facility.")
    if valid_until is not None and valid_until <= timezone.now():
        raise ConflictError("valid_until must be in the future.")

    _require_grantable(
        actor,
        list(role.permissions.values_list("codename", flat=True)),
        facility_id=facility.pk if facility else None,
        department_id=department.pk if department else None,
    )
    if RoleAssignment.objects.filter(
        user=user, role=role, facility=facility, department=department, revoked_at__isnull=True
    ).exists():
        raise ConflictError("The user already holds this role at this scope.")
    return facility


def sync_system_roles() -> None:
    """Keep system roles' permissions in line with ``SYSTEM_ROLES`` as the catalog grows
    (e.g. a new permission added to the administrator role after provisioning)."""
    from apps.organizations.models import Organization

    for organization in Organization.objects.all():
        create_system_roles(organization)  # roles added to the catalog after provisioning
    for code, definition in SYSTEM_ROLES.items():
        wanted = Permission.objects.filter(codename__in=definition["permissions"])
        for role in Role.objects.filter(code=code, is_system=True):
            role.permissions.add(*wanted)


@transaction.atomic
def assign_role(
    *,
    actor,
    user,
    role: Role,
    facility: Facility | None = None,
    department: Department | None = None,
    valid_until=None,
    reason: str = "",
    request=None,
    valid_from=None,
    delegation=None,
    delegated_from: RoleAssignment | None = None,
) -> RoleAssignment:
    """Grant a role. ``valid_from``/``delegation``/``delegated_from`` are used by cover
    arrangements (delegations.py) to lend a copy of another person's assignment."""
    facility = validate_role_assignment(
        actor=actor,
        user=user,
        role=role,
        facility=facility,
        department=department,
        valid_until=valid_until,
    )
    assignment = RoleAssignment.objects.create(
        organization_id=role.organization_id,
        user=user,
        role=role,
        facility=facility,
        department=department,
        valid_from=valid_from or timezone.now(),
        valid_until=valid_until,
        reason=reason,
        granted_by=actor,
        delegation=delegation,
        delegated_from=delegated_from,
    )
    clear_permission_cache(user)
    record_audit_event(
        action=AuditAction.ROLE_ASSIGNED,
        resource_type="role_assignment",
        resource_id=assignment.pk,
        facility_id=facility.pk if facility else None,
        actor=actor,
        request=request,
        reason=reason,
        metadata={
            "user_id": str(user.pk),
            "role": role.code,
            "department_id": str(department.pk) if department else None,
            **({"delegation_id": str(delegation.pk)} if delegation is not None else {}),
        },
    )
    return assignment


def _ensure_not_last_administrator_grant(assignment: RoleAssignment) -> None:
    """Never remove the hospital's last organization administrator role (no lock-out)."""
    from apps.identity.accounts import ADMIN_ROLE, active_administrators

    role = assignment.role
    if assignment.delegation_id is not None:
        return  # lent cover access never counts as one of the hospital's administrators
    if role.code != ADMIN_ROLE or not role.is_system or assignment.facility_id is not None:
        return
    if not active_administrators().exclude(pk=assignment.user_id).exists():
        raise ConflictError(
            "This is the last active hospital administrator. Give another person the "
            "Organization administrator role first, so the hospital is never locked out.",
            code="LAST_ADMINISTRATOR",
        )


def close_assignment(
    assignment: RoleAssignment, *, actor, reason: str, request=None, metadata=None
) -> None:
    """Revoke one assignment and record it (no permission rules; callers check those).
    Copies lent to someone covering for this person end with it (HIMS-IAM-017)."""
    assignment.revoked_at = timezone.now()
    assignment.revoked_by = actor
    assignment.revocation_reason = reason
    assignment.save(update_fields=["revoked_at", "revoked_by", "revocation_reason", "updated_at"])
    clear_permission_cache(assignment.user)
    record_audit_event(
        action=AuditAction.ROLE_REVOKED,
        resource_type="role_assignment",
        resource_id=assignment.pk,
        facility_id=assignment.facility_id,
        actor=actor,
        request=request,
        reason=reason,
        metadata={
            "user_id": str(assignment.user_id),
            "role_id": str(assignment.role_id),
            **(metadata or {}),
        },
    )
    copies = RoleAssignment.objects.select_for_update().filter(
        delegated_from=assignment, revoked_at__isnull=True
    )
    for copy in copies:
        close_assignment(
            copy,
            actor=actor,
            reason="The covered person's own access ended, so the cover for it ended too.",
            request=request,
            metadata={"delegation_id": str(copy.delegation_id), "cascade": True},
        )


@transaction.atomic
def revoke_role_assignment(*, actor, assignment_id, reason: str, request=None) -> RoleAssignment:
    assignment = RoleAssignment.objects.select_for_update().get(pk=assignment_id)
    if assignment.revoked_at is not None:
        raise ConflictError("This role assignment is already revoked.")
    if actor is not None and assignment.user_id == actor.pk:
        raise ConflictError("You cannot revoke your own role assignments.")
    _ensure_not_last_administrator_grant(assignment)
    close_assignment(assignment, actor=actor, reason=reason, request=request)
    return assignment


@transaction.atomic
def update_role(
    *, actor, role_id, version: int, request=None, name=None, description=None, permissions=None
) -> Role:
    """Change a custom role. System roles follow the catalog and cannot be edited here.

    Added permissions must be held by the actor (no privilege escalation). Everyone holding the
    role gets the new permissions at once.
    """
    role = lock_for_update(Role, pk=role_id, expected_version=version)
    if role.is_system:
        raise ConflictError(
            "System roles are kept in line with the catalog and cannot be edited. Create a "
            "custom role instead.",
            code="SYSTEM_ROLE_READ_ONLY",
        )
    before = {
        "name": role.name,
        "description": role.description,
        "permissions": sorted(role.permissions.values_list("codename", flat=True)),
    }
    if permissions is not None:
        unknown = [p for p in permissions if p not in PERMISSIONS]
        if unknown:
            raise ConflictError(f"Unknown permissions: {', '.join(sorted(unknown))}")
        added = set(permissions) - set(before["permissions"])
        _require_grantable(actor, added)
        role.permissions.set(Permission.objects.filter(codename__in=permissions))
    if name is not None:
        role.name = name
    if description is not None:
        role.description = description
    bump_version(role)
    role.save()
    after = {
        "name": role.name,
        "description": role.description,
        "permissions": sorted(role.permissions.values_list("codename", flat=True)),
    }
    if actor is not None:
        clear_permission_cache(actor)  # others pick up the change on their next request
    changed = [key for key in after if before[key] != after[key]]
    record_audit_event(
        action=AuditAction.ROLE_UPDATED,
        resource_type="role",
        resource_id=role.pk,
        actor=actor,
        request=request,
        changes={
            "before": {key: before[key] for key in changed},
            "after": {key: after[key] for key in changed},
        },
    )
    return role
