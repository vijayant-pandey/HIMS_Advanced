"""HIMS-UI-002: users without access see a reference number that is stored in the audit log."""

import pytest

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction


@pytest.mark.django_db
def test_no_access_page_visit_is_audited_with_its_reference(client_for, make_user, organization):
    user = make_user()  # signed in, but holds no role
    response = client_for(user).post("/api/v1/auth/no-access-report/", {"page": "/"}, format="json")
    assert response.status_code == 201
    reference = response.json()["reference"]
    assert reference == response["X-Request-ID"]

    event = AuditEvent.objects.get(action=AuditAction.ACCESS_NONE_ASSIGNED)
    assert event.request_id == reference  # an admin can search the audit log for it
    assert event.actor_id == user.pk
    assert event.outcome == AuditEvent.Outcome.DENIED
    assert event.metadata == {"page": "/", "grant_count": 0}


@pytest.mark.django_db
def test_no_access_report_requires_sign_in(client_for, organization):
    assert client_for().post("/api/v1/auth/no-access-report/", {}, format="json").status_code == 401


@pytest.mark.django_db
def test_permission_denied_reference_matches_the_audit_event(client_for, make_user, organization):
    user = make_user()
    response = client_for(user).get("/api/v1/facilities/")
    assert response.status_code == 403
    reference = response.json()["request_id"]

    event = AuditEvent.objects.get(action=AuditAction.ACCESS_DENIED, actor_id=user.pk)
    assert event.request_id == reference


@pytest.mark.django_db
def test_auditor_can_find_an_event_by_reference(client_for, make_user, auditor_user):
    user = make_user()
    reference = client_for(user).get("/api/v1/facilities/").json()["request_id"]
    found = client_for(auditor_user).get("/api/v1/audit-events/", {"action": "access.denied"})
    assert reference in {row["request_id"] for row in found.json()["results"]}
