"""Authorization and scope isolation (spec 13.2, 13.5, 26.4)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.access_control.catalog import P
from apps.access_control.models import RoleAssignment
from apps.access_control.services import create_role
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction


@pytest.fixture
def department_manager_role(organization):
    return create_role(
        actor=None,
        organization=organization,
        code="department-manager",
        name="Department manager",
        permissions=[P.DEPARTMENTS_VIEW, P.DEPARTMENTS_MANAGE, P.FACILITIES_VIEW],
    )


@pytest.fixture
def facility_a_manager(make_user, department_manager_role, facility_a):
    return make_user(role=department_manager_role, facility=facility_a)


def _department(facility, code="new-dept"):
    return {
        "facility": str(facility.pk),
        "code": code,
        "name": "New",
        "department_type": "clinical",
    }


@pytest.mark.django_db
def test_user_without_any_role_is_denied(client_for, make_user, organization):
    response = client_for(make_user()).get("/api/v1/facilities/")
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_facility_scoped_user_only_sees_their_facility(
    client_for, facility_a_manager, facility_a, facility_b
):
    response = client_for(facility_a_manager).get("/api/v1/facilities/")
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["results"]] == [str(facility_a.pk)]

    other = client_for(facility_a_manager).get(f"/api/v1/facilities/{facility_b.pk}/")
    assert other.status_code == 404  # existence is not revealed


@pytest.mark.django_db
def test_cannot_create_in_another_facility_and_denial_is_audited(
    client_for, facility_a_manager, facility_a, facility_b
):
    client = client_for(facility_a_manager)
    assert (
        client.post("/api/v1/departments/", _department(facility_a), format="json").status_code
        == 201
    )

    denied = client.post("/api/v1/departments/", _department(facility_b, "x"), format="json")
    assert denied.status_code == 403
    assert AuditEvent.objects.filter(
        action=AuditAction.ACCESS_DENIED,
        actor_id=facility_a_manager.pk,
        outcome=AuditEvent.Outcome.DENIED,
    ).exists()


@pytest.mark.django_db
def test_facility_scoped_user_cannot_create_facilities(client_for, facility_a_manager):
    response = client_for(facility_a_manager).post("/api/v1/facilities/", {}, format="json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_revoked_assignment_removes_access(client_for, admin_user, facility_a_manager):
    assignment = RoleAssignment.objects.get(user=facility_a_manager)
    response = client_for(admin_user).post(
        f"/api/v1/role-assignments/{assignment.pk}/revoke/",
        {"reason": "Left the department"},
        format="json",
    )
    assert response.status_code == 200
    assert client_for(facility_a_manager).get("/api/v1/departments/").status_code == 403


@pytest.mark.django_db
def test_expired_assignment_grants_nothing(client_for, facility_a_manager):
    RoleAssignment.objects.filter(user=facility_a_manager).update(
        valid_from=timezone.now() - timedelta(days=2),
        valid_until=timezone.now() - timedelta(days=1),
    )
    assert client_for(facility_a_manager).get("/api/v1/departments/").status_code == 403


@pytest.mark.django_db
def test_inactive_user_loses_all_grants(client_for, facility_a_manager):
    client = client_for(facility_a_manager)
    facility_a_manager.is_active = False
    facility_a_manager.save(update_fields=["is_active"])
    assert client.get("/api/v1/departments/").status_code in (401, 403)


@pytest.mark.django_db
def test_admin_cannot_grant_permissions_they_do_not_hold(
    client_for, admin_user, system_roles, make_user
):
    target = make_user()
    response = client_for(admin_user).post(
        "/api/v1/role-assignments/",
        {"user": str(target.pk), "role": str(system_roles["auditor"].pk), "reason": "test"},
        format="json",
    )
    assert response.status_code == 403
    assert not RoleAssignment.objects.filter(user=target).exists()


@pytest.mark.django_db
def test_department_must_belong_to_facility(
    client_for, admin_user, department_manager_role, make_user, facility_b, department_a
):
    response = client_for(admin_user).post(
        "/api/v1/role-assignments/",
        {
            "user": str(make_user().pk),
            "role": str(department_manager_role.pk),
            "facility": str(facility_b.pk),
            "department": str(department_a.pk),
            "reason": "test",
        },
        format="json",
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_users_cannot_revoke_their_own_access(client_for, admin_user):
    assignment = RoleAssignment.objects.get(user=admin_user)
    response = client_for(admin_user).post(
        f"/api/v1/role-assignments/{assignment.pk}/revoke/", {"reason": "oops"}, format="json"
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_every_api_view_declares_permissions():
    """Default deny is only meaningful if no DRF view silently falls back to it by accident.
    Every view must either declare required_permissions or explicitly override the
    permission classes."""
    from django.urls import get_resolver
    from rest_framework.views import APIView

    from common.permissions import ScopedPermission

    def walk(patterns):
        for pattern in patterns:
            if hasattr(pattern, "url_patterns"):
                yield from walk(pattern.url_patterns)
            else:
                yield pattern.callback

    missing = []
    for callback in walk(get_resolver().url_patterns):
        view_class = getattr(callback, "cls", None)
        if view_class is None or not issubclass(view_class, APIView):
            continue
        uses_scoped = ScopedPermission in view_class.permission_classes
        if uses_scoped and not getattr(view_class, "required_permissions", None):
            missing.append(view_class.__name__)
    assert missing == []
