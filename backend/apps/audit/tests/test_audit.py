import pytest
from django.db import DatabaseError, connection, transaction

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction, record_audit_event


@pytest.fixture
def event(organization):
    return record_audit_event(action="test.event", resource_type="thing", resource_id="1")


@pytest.mark.django_db
def test_database_rejects_update(event):
    with (
        pytest.raises(DatabaseError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("UPDATE audit_events SET action = 'tampered' WHERE id = %s", [event.pk])


@pytest.mark.django_db
def test_database_rejects_delete(event):
    with (
        pytest.raises(DatabaseError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("DELETE FROM audit_events WHERE id = %s", [event.pk])


@pytest.mark.django_db
def test_orm_refuses_update_and_delete(event):
    with pytest.raises(RuntimeError):
        event.save()
    with pytest.raises(RuntimeError):
        event.delete()


@pytest.mark.django_db
def test_sensitive_fields_are_redacted_in_snapshots(admin_user):
    from apps.audit.services import snapshot

    assert snapshot(admin_user, ["password", "email"])["password"] == "[REDACTED]"


@pytest.mark.django_db
def test_audit_search_requires_audit_permission(client_for, admin_user):
    # Separation of duties: organization administrators cannot read the audit log.
    response = client_for(admin_user).get("/api/v1/audit-events/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_auditor_can_search_and_search_is_audited(client_for, auditor_user, admin_user):
    response = client_for(auditor_user).get(
        "/api/v1/audit-events/", {"action": AuditAction.ROLE_ASSIGNED}
    )
    assert response.status_code == 200
    assert response.json()["count"] >= 1
    assert AuditEvent.objects.filter(
        action=AuditAction.AUDIT_SEARCHED, actor_id=auditor_user.pk
    ).exists()
