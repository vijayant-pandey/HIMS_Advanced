"""Audit log screen for auditors (HIMS-AUD-003). All data is synthetic."""

import csv
import io

import pytest
from django.test import Client

from apps.audit import catalog
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction, record_audit_event

API = "/api/v1/audit-events"


def test_every_audit_action_has_a_plain_label():
    actions = [v for k, v in vars(AuditAction).items() if k.isupper()]
    missing = [a for a in actions if a not in catalog.LABELS]
    assert missing == [], f"Add labels to apps/audit/catalog.py: {missing}"


def test_admin_console_events_get_generated_labels():
    assert catalog.label("admin.department.updated") == "Admin console: department changed"
    assert catalog.category("admin.department.updated") == "Admin console"


@pytest.mark.django_db
def test_list_shows_who_where_and_what(client_for, auditor_user, admin_user, facility_a):
    record_audit_event(
        action=AuditAction.FACILITY_UPDATED,
        resource_type="facility",
        resource_id=facility_a.pk,
        facility_id=facility_a.pk,
        actor=admin_user,
        changes={"before": {"phone": ""}, "after": {"phone": "+91"}},
    )
    rows = client_for(auditor_user).get(API + "/", {"action": "facility.updated"}).json()["results"]
    assert len(rows) == 1
    row = rows[0]
    assert row["action_label"] == "Facility changed"
    assert row["category"] == "Hospital setup"
    assert row["actor_name"] == admin_user.display_name
    assert row["actor_email"] == admin_user.email
    assert row["facility_name"] == "Facility FAC-A"


@pytest.mark.django_db
def test_find_by_reference_person_category_and_day(client_for, auditor_user, make_user):
    nurse = make_user(display_name="Synthetic Nurse Rekha", email="rekha@synthetic.test")
    # Created in one step: audit rows can never be edited afterwards (append-only trigger).
    event = AuditEvent.objects.create(
        action=AuditAction.ACCESS_DENIED,
        resource_type="api",
        actor_type=AuditEvent.ActorType.USER,
        actor_id=nurse.pk,
        outcome=AuditEvent.Outcome.DENIED,
        request_id="ref-4242-abcd",
    )
    client = client_for(auditor_user)

    by_ref = client.get(API + "/", {"request_id": "REF-4242-ABCD"}).json()["results"]
    assert [r["id"] for r in by_ref] == [str(event.pk)]
    by_person = client.get(API + "/", {"person": "rekha"}).json()["results"]
    assert {r["action"] for r in by_person} == {"access.denied"}
    by_category = client.get(API + "/", {"category": "access", "outcome": "denied"}).json()
    assert by_category["count"] == 1
    today = event.occurred_at.date().isoformat()
    assert (
        client.get(API + "/", {"date_from": today, "date_to": today, "person": "rekha"}).json()[
            "count"
        ]
        == 1
    )


@pytest.mark.django_db
def test_bad_filters_give_a_clear_message_not_a_server_error(client_for, auditor_user):
    client = client_for(auditor_user)
    for params in ({"actor_id": "not-a-uuid"}, {"date_from": "31/12/2026"}, {"outcome": "maybe"}):
        response = client.get(API + "/", params)
        assert response.status_code == 400, params
        assert response.json()["errors"]


@pytest.mark.django_db
def test_only_auditors_can_search(client_for, admin_user, make_user, system_roles):
    assert client_for(admin_user).get(API + "/").status_code == 403  # separation of duties
    staff = make_user(role=system_roles["basic-staff"])
    assert client_for(staff).get(API + "/export/").status_code == 403


@pytest.mark.django_db
def test_searching_is_itself_audited(client_for, auditor_user):
    client_for(auditor_user).get(API + "/", {"category": "auth"})
    event = AuditEvent.objects.get(action=AuditAction.AUDIT_SEARCHED)
    assert event.actor_id == auditor_user.pk
    assert event.metadata["filters"] == {"category": "auth"}


@pytest.mark.django_db
def test_export_csv_is_safe_limited_and_audited(client_for, auditor_user, admin_user):
    record_audit_event(
        action=AuditAction.ROLE_REVOKED,
        resource_type="role_assignment",
        actor=admin_user,
        reason="=HYPERLINK(evil)",  # must not become a spreadsheet formula
    )
    response = client_for(auditor_user).get(API + "/export/", {"action": "access.role.revoked"})
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert "attachment;" in response["Content-Disposition"]
    assert response["X-Export-Truncated"] == "false"
    rows = list(csv.reader(io.StringIO(b"".join(response.streaming_content).decode())))
    assert rows[0][:3] == ["When (UTC)", "What happened", "Action code"]
    assert rows[1][1] == "Access removed"
    assert rows[1][4] == admin_user.display_name
    assert rows[1][9] == "'=HYPERLINK(evil)"
    exported = AuditEvent.objects.get(action=AuditAction.AUDIT_EXPORTED)
    assert exported.metadata["rows"] == 1 and exported.metadata["truncated"] is False


@pytest.mark.django_db
def test_action_list_for_the_filter(client_for, auditor_user):
    actions = client_for(auditor_user).get(API + "/actions/").json()
    assert {
        "action": "auth.login",
        "label": "Signed in",
        "category": "Sign-in and security",
    } in actions


@pytest.mark.django_db
def test_admin_console_audit_page_shows_plain_words(auditor_user, admin_user):
    record_audit_event(action=AuditAction.AUTH_LOGIN, resource_type="session", actor=admin_user)
    console = Client()
    console.force_login(auditor_user)
    page = console.get("/admin/audit/auditevent/")
    assert page.status_code == 200
    assert b"Signed in" in page.content
    assert admin_user.display_name.encode() in page.content
