"""Which staff a person may see (HIMS-STAFF-008; spec 4.4 "facility- and department-level
restrictions", 13.2 least privilege).

A hospital-wide grant sees everyone. A facility grant sees the staff posted (now or starting
later) in that facility's departments; a department grant sees the staff posted in that
department. People with no current posting are visible only to hospital-wide grants (HR).
Ended postings do not count: someone who moved on is no longer "your" staff.
"""

from django.db.models import Q

from apps.access_control.selectors import get_permission_scope
from apps.facilities.closing import current_postings_q

from .models import StaffDepartmentAssignment


def _postings_in_scope(scope, prefix: str = "") -> Q:
    q = Q(**{f"{prefix}department__facility_id__in": scope.facility_ids})
    for facility_id, department_id in scope.department_ids:
        q |= Q(
            **{
                f"{prefix}department__facility_id": facility_id,
                f"{prefix}department_id": department_id,
            }
        )
    return q


def visible_staff_ids(user, codename: str):
    """A subquery of visible staff ids, or None when the grant is hospital-wide."""
    scope = get_permission_scope(user, codename)
    if scope.org_wide:
        return None
    return StaffDepartmentAssignment.objects.filter(
        current_postings_q(), _postings_in_scope(scope)
    ).values("staff_id")


def limit_to_visible(queryset, user, codename: str, *, staff_field: str = "pk"):
    """``queryset`` restricted to the staff this grant covers (rows of others vanish: 404)."""
    ids = visible_staff_ids(user, codename)
    return queryset if ids is None else queryset.filter(**{f"{staff_field}__in": ids})


def scope_context(user, codename: str, staff_id) -> tuple:
    """A (facility, department) pair of this person's current postings that the grant covers,
    for the object-level permission check; (None, None) when there is none."""
    scope = get_permission_scope(user, codename)
    if scope.org_wide:
        return None, None  # covered anyway
    pairs = StaffDepartmentAssignment.objects.filter(
        current_postings_q(), staff_id=staff_id
    ).values_list("department__facility_id", "department_id")
    for facility_id, department_id in pairs:
        if scope.covers(facility_id=facility_id, department_id=department_id):
            return facility_id, department_id
    return None, None
