"""Authorization queries. All permission decisions in the API go through here."""

from collections import defaultdict
from dataclasses import dataclass, field
from uuid import UUID

from django.db.models import Q
from django.utils import timezone

from common.exceptions import ScopeViolation

from .models import RoleAssignment

_CACHE_ATTR = "_hims_permission_index"


@dataclass(frozen=True)
class PermissionScope:
    org_wide: bool = False
    facility_ids: frozenset[UUID] = field(default_factory=frozenset)
    department_ids: frozenset[tuple[UUID, UUID]] = field(default_factory=frozenset)

    @property
    def is_empty(self) -> bool:
        return not (self.org_wide or self.facility_ids or self.department_ids)

    def covers(self, *, facility_id=None, department_id=None) -> bool:
        if self.org_wide:
            return True
        if facility_id is None:
            return False
        if facility_id in self.facility_ids:
            return True
        return department_id is not None and (facility_id, department_id) in self.department_ids

    def visible_facility_ids(self) -> frozenset[UUID] | None:
        """None means every facility; otherwise the facilities any grant touches."""
        if self.org_wide:
            return None
        return self.facility_ids | frozenset(f for f, _ in self.department_ids)


def _active_assignments(user):
    now = timezone.now()
    return RoleAssignment.objects.filter(
        Q(valid_until__isnull=True) | Q(valid_until__gt=now),
        user=user,
        revoked_at__isnull=True,
        valid_from__lte=now,
        role__role_permissions__permission__is_active=True,
    )


def _permission_index(user) -> dict[str, list[tuple[UUID | None, UUID | None]]]:
    """All active grants for the user, computed once per request (cached on the user)."""
    cached = getattr(user, _CACHE_ATTR, None)
    if cached is not None:
        return cached
    index: dict[str, list] = defaultdict(list)
    rows = _active_assignments(user).values_list(
        "role__role_permissions__permission__codename", "facility_id", "department_id"
    )
    for codename, facility_id, department_id in rows:
        index[codename].append((facility_id, department_id))
    setattr(user, _CACHE_ATTR, index)
    return index


def clear_permission_cache(user) -> None:
    if hasattr(user, _CACHE_ATTR):
        delattr(user, _CACHE_ATTR)


def get_permission_scope(user, codename: str) -> PermissionScope:
    if not (user and user.is_authenticated and user.is_active):
        return PermissionScope()
    grants = _permission_index(user).get(codename, [])
    org_wide = any(facility is None for facility, _ in grants)
    facilities = frozenset(f for f, d in grants if f is not None and d is None)
    departments = frozenset((f, d) for f, d in grants if f is not None and d is not None)
    return PermissionScope(org_wide=org_wide, facility_ids=facilities, department_ids=departments)


def has_permission(user, codename: str, *, facility_id=None, department_id=None) -> bool:
    return get_permission_scope(user, codename).covers(
        facility_id=facility_id, department_id=department_id
    )


def check_permission(user, codename: str, *, facility_id=None, department_id=None) -> None:
    """Raise ScopeViolation (rendered as 403 and audited) unless the grant covers the scope."""
    if not has_permission(user, codename, facility_id=facility_id, department_id=department_id):
        raise ScopeViolation("You do not have permission to perform this action for this scope.")


def list_grants(user) -> list[dict]:
    return [
        {"permission": codename, "facility_id": facility_id, "department_id": department_id}
        for codename, grants in sorted(_permission_index(user).items())
        for facility_id, department_id in grants
    ]
