"""What must be finished before a department or facility can be deactivated (HIMS-FAC-006).

Closing things in order (like locations: "deactivate everything inside it first") prevents
staff, access or wards from silently pointing at something that no longer operates. The checks
run in ``Department.clean`` / ``Facility.clean``, so the app, the API and the admin console all
apply them. Other apps are imported lazily: facilities sits below them.
"""

from django.db.models import Q
from django.utils import timezone


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def _active_grants(**scope):
    from apps.access_control.models import RoleAssignment

    now = timezone.now()
    return RoleAssignment.objects.filter(revoked_at__isnull=True, **scope).filter(
        Q(valid_until__isnull=True) | Q(valid_until__gt=now)
    )


def current_postings_q(prefix: str = "") -> Q:
    """Postings that are current or start in the future (not yet ended)."""
    today = timezone.localdate()
    return Q(**{f"{prefix}valid_until__isnull": True}) | Q(**{f"{prefix}valid_until__gte": today})


def department_blockers(department) -> list[str]:
    from apps.staff.models import StaffDepartmentAssignment

    from .models import Ward

    blockers = []
    postings = StaffDepartmentAssignment.objects.filter(
        current_postings_q(), department=department
    ).count()
    if postings:
        blockers.append(
            f"{_plural(postings, 'staff member is', 'staff members are')} posted here "
            "(end their postings on the Staff page)"
        )
    grants = _active_grants(department=department).count()
    if grants:
        blockers.append(
            f"{_plural(grants, 'person has', 'people have')} access limited to this department "
            "(remove it on the Access page)"
        )
    wards = Ward.objects.filter(department=department, is_active=True).count()
    if wards:
        blockers.append(
            f"{_plural(wards, 'active ward belongs', 'active wards belong')} to it "
            "(deactivate or reassign them on the Locations page)"
        )
    return blockers


def facility_blockers(facility) -> list[str]:
    from .models import Building, Department

    blockers = []
    departments = Department.objects.filter(
        facility=facility, status=Department.Status.ACTIVE
    ).count()
    if departments:
        blockers.append(
            f"{_plural(departments, 'department is', 'departments are')} still active "
            "(deactivate them first)"
        )
    buildings = Building.objects.filter(facility=facility, is_active=True).count()
    if buildings:
        blockers.append(
            f"{_plural(buildings, 'building is', 'buildings are')} still active "
            "(deactivate them on the Locations page)"
        )
    grants = _active_grants(facility=facility).count()
    if grants:
        blockers.append(
            f"{_plural(grants, 'person has', 'people have')} access at this facility "
            "(remove it on the Access page)"
        )
    return blockers


def explain(blockers: list[str]) -> str:
    return "It cannot be deactivated yet: " + "; ".join(blockers) + "."


# --- Department head (HIMS-FAC-007) ------------------------------------------------------------


def head_problem(department, staff) -> str | None:
    """Why this person cannot lead the department, or None when they can."""
    from apps.staff.models import StaffDepartmentAssignment, StaffMember

    working = (StaffMember.EmploymentStatus.ACTIVE, StaffMember.EmploymentStatus.ON_LEAVE)
    if staff.employment_status not in working:
        return "The head must be a working staff member (not suspended or terminated)."
    today = timezone.localdate()
    posted = StaffDepartmentAssignment.objects.filter(
        current_postings_q(), staff=staff, department=department, valid_from__lte=today
    ).exists()
    if not posted:
        return "The head must currently be posted in this department (add a posting first)."
    return None


def clear_head_if_invalid(department, *, reason: str, actor=None, request=None) -> bool:
    """Remove a head who no longer qualifies (posting ended, employment ended). Audited."""
    from apps.audit.services import AuditAction, record_audit_event

    if department.head_id is None or head_problem(department, department.head) is None:
        return False
    previous = department.head_id
    department.head = None
    department.version += 1
    department.save(update_fields=["head", "version", "updated_at"])
    record_audit_event(
        action=AuditAction.DEPARTMENT_UPDATED,
        resource_type="department",
        resource_id=department.pk,
        facility_id=department.facility_id,
        actor=actor,
        request=request,
        reason=reason,
        changes={"before": {"head": str(previous)}, "after": {"head": None}},
    )
    return True
