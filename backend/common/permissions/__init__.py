"""Default-deny, scope-aware API authorization (spec 13.2, 26.4).

Every view declares ``required_permissions``: a mapping of viewset action (or lower-case HTTP
method for plain APIViews) to a permission codename. Anything not declared is denied.

``permission_scope`` sets how the grant is evaluated:

* ``"organization"`` (default): the user needs an organization-wide grant.
* ``"facility"``: a grant at any facility/department lets the request through; querysets must
  then be filtered with ``visible_facility_ids`` and objects are checked against their own
  facility/department via ``get_permission_context(obj)``.

Hidden UI controls are never a security boundary; this class is.
"""

from rest_framework.permissions import BasePermission

ORGANIZATION = "organization"
FACILITY = "facility"


def required_permission(request, view) -> str | None:
    mapping = getattr(view, "required_permissions", None) or {}
    action = getattr(view, "action", None) or request.method.lower()
    return mapping.get(action)


def filter_by_facility_scope(view, queryset, *, facility_field: str = "facility_id"):
    """Restrict a queryset to facilities the user's grant for the current action covers.

    Out-of-scope rows become invisible (404), which avoids revealing that they exist.
    """
    if getattr(view, "swagger_fake_view", False):
        return queryset.none()
    codename = required_permission(view.request, view)
    if codename is None:
        return queryset.none()

    from apps.access_control.selectors import get_permission_scope

    visible = get_permission_scope(view.request.user, codename).visible_facility_ids()
    if visible is None:
        return queryset
    return queryset.filter(**{f"{facility_field}__in": visible})


class ScopedPermission(BasePermission):
    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        codename = required_permission(request, view)
        if codename is None:
            return False

        from apps.access_control.selectors import get_permission_scope

        scope = get_permission_scope(user, codename)
        if getattr(view, "permission_scope", ORGANIZATION) == FACILITY:
            return not scope.is_empty
        return scope.org_wide

    def has_object_permission(self, request, view, obj) -> bool:
        if getattr(view, "permission_scope", ORGANIZATION) != FACILITY:
            return True
        codename = required_permission(request, view)
        if codename is None:
            return False

        from apps.access_control.selectors import get_permission_scope

        facility_id, department_id = view.get_permission_context(obj)
        return get_permission_scope(request.user, codename).covers(
            facility_id=facility_id, department_id=department_id
        )
