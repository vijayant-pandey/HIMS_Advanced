"""Compliance registers and incident deadlines (HIMS-COMP; spec 13, 23, 26.7). Synthetic data."""

from datetime import UTC, datetime, timedelta

import pytest
from django.core import mail
from django.test import Client
from django.utils import timezone

from apps.access_control.catalog import PERMISSIONS, SYSTEM_ROLES, P
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.compliance import catalog, docs_generator
from apps.compliance.incidents import required_deadlines, send_deadline_alerts
from apps.compliance.models import (
    ComplianceRequirement,
    IncidentNotification,
    RiskEntry,
    SecurityIncident,
)
from apps.compliance.services import sync_catalog
from apps.notifications.models import Notification

REQ = "/api/v1/compliance-requirements/"
RISK = "/api/v1/compliance-risks/"
INC = "/api/v1/security-incidents/"
T0 = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)


def _country(organization, code):
    organization.country = code
    organization.save(update_fields=["country"])


def _incident(**extra):
    return SecurityIncident(title="t", description="d", detected_at=T0, **extra)


def test_generated_compliance_documents_match_the_catalog():
    for path, text in docs_generator.outputs().items():
        committed = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        assert committed == text, f"{path.name} is stale: run python manage.py compliance_docs"


def test_catalog_codes_are_unique_and_nothing_starts_as_verified():
    codes = [row[0] for row in catalog.REQUIREMENTS]
    assert len(codes) == len(set(codes))
    assert {row[7] for row in catalog.REQUIREMENTS} <= {catalog.NS, catalog.IP, catalog.DONE}


def test_only_the_compliance_officer_and_administrator_can_manage():
    assert P.COMPLIANCE_MANAGE in SYSTEM_ROLES["compliance-officer"]["permissions"]
    assert P.COMPLIANCE_MANAGE not in SYSTEM_ROLES["auditor"]["permissions"]
    assert P.COMPLIANCE_VIEW in SYSTEM_ROLES["auditor"]["permissions"]
    assert P.COMPLIANCE_VIEW in PERMISSIONS


# --- Legal deadlines ------------------------------------------------------------------------


def test_india_cyber_incident_needs_cert_in_within_6_hours():
    due = required_deadlines(_incident(personal_data_affected=False), "IN")
    assert due == {IncidentNotification.Kind.CERT_IN: T0 + timedelta(hours=6)}


def test_india_personal_data_breach_adds_board_and_people():
    due = required_deadlines(_incident(personal_data_affected=True), "IN")
    assert due[IncidentNotification.Kind.DPDP_BOARD_DETAILED] == T0 + timedelta(hours=72)
    assert IncidentNotification.Kind.DPDP_BOARD_INITIAL in due
    assert IncidentNotification.Kind.DPDP_PEOPLE in due


@pytest.mark.parametrize(
    ("people", "hhs_due", "media"),
    [
        (None, T0 + timedelta(days=60), False),  # unknown: treated as the earlier deadline
        (499, datetime(2027, 1, 1, tzinfo=UTC) + timedelta(days=60), False),
        (500, T0 + timedelta(days=60), False),
        (501, T0 + timedelta(days=60), True),
    ],
)
def test_us_breach_deadlines_follow_the_number_of_people(people, hhs_due, media):
    due = required_deadlines(_incident(personal_data_affected=True, people_affected=people), "US")
    assert due[IncidentNotification.Kind.HIPAA_INDIVIDUALS] == T0 + timedelta(days=60)
    assert due[IncidentNotification.Kind.HIPAA_HHS] == hhs_due
    assert (IncidentNotification.Kind.HIPAA_MEDIA in due) is media


def test_us_incident_without_personal_data_needs_no_notice():
    assert required_deadlines(_incident(personal_data_affected=False), "US") == {}


# --- Requirements ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_requirements_follow_the_hospital_country(client_for, admin_user, organization):
    _country(organization, "IN")
    codes = {row["code"] for row in client_for(admin_user).get(REQ).json()}
    assert "CERTIN-REPORTING" in codes and "ALL-THREAT-MODEL" in codes
    assert "HIPAA-SEC-RISK-ANALYSIS" not in codes
    _country(organization, "US")
    codes = {row["code"] for row in client_for(admin_user).get(REQ).json()}
    assert "HIPAA-SEC-RISK-ANALYSIS" in codes and "CERTIN-REPORTING" not in codes


@pytest.mark.django_db
def test_verifying_needs_evidence_and_is_audited(client_for, admin_user, organization):
    _country(organization, "IN")
    client = client_for(admin_user)
    item = ComplianceRequirement.objects.get(code="CERTIN-REPORTING")
    refused = client.patch(
        f"{REQ}{item.pk}/", {"version": item.version, "status": "verified"}, format="json"
    )
    assert refused.status_code == 409 and refused.json()["code"] == "NO_EVIDENCE"
    done = client.patch(
        f"{REQ}{item.pk}/",
        {
            "version": item.version,
            "status": "verified",
            "evidence": "Drill report 2026-11",
            "owner": "R",
        },
        format="json",
    )
    assert done.status_code == 200 and done.json()["status"] == "verified"
    assert done.json()["reviewed_by_name"] == admin_user.display_name
    assert AuditEvent.objects.filter(action=AuditAction.COMPLIANCE_REQUIREMENT_UPDATED).exists()
    stale = client.patch(f"{REQ}{item.pk}/", {"version": item.version, "owner": "x"}, format="json")
    assert stale.status_code == 409


@pytest.mark.django_db
def test_catalog_sync_keeps_the_hospital_answers():
    item = ComplianceRequirement.objects.get(code="HIPAA-SEC-OFFICER")
    item.status = ComplianceRequirement.Status.VERIFIED
    item.owner = "Synthetic Officer"
    item.save()
    sync_catalog()
    item.refresh_from_db()
    assert item.status == ComplianceRequirement.Status.VERIFIED
    assert item.owner == "Synthetic Officer"


# --- Risks ----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_add_and_accept_a_risk(client_for, admin_user):
    client = client_for(admin_user)
    created = client.post(
        RISK,
        {"title": "New risk", "description": "d", "category": "data", "likelihood": 5, "impact": 4},
        format="json",
    )
    assert created.status_code == 201
    body = created.json()
    assert body["score"] == 20 and body["code"].startswith("R-")
    url = f"{RISK}{body['id']}/"
    refused = client.patch(url, {"version": 1, "status": "accepted"}, format="json")
    assert refused.json()["code"] == "REASON_REQUIRED"
    accepted = client.patch(
        url,
        {"version": 1, "status": "accepted", "acceptance_reason": "Low exposure"},
        format="json",
    )
    assert accepted.status_code == 200
    bad = client.post(
        RISK, {"title": "x", "description": "d", "category": "c", "impact": 9}, format="json"
    )
    assert bad.status_code == 400


# --- Incidents ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_any_signed_in_person_can_report_but_not_read(
    client_for, make_user, admin_user, organization, django_capture_on_commit_callbacks
):
    _country(organization, "IN")
    staff = client_for(make_user(display_name="Plain Staff"))
    with django_capture_on_commit_callbacks(execute=True):
        response = staff.post(
            INC, {"title": "Lost laptop", "description": "Left on a train"}, format="json"
        )
    assert response.status_code == 201
    assert "notifications" not in response.json()  # the reporter gets a receipt only
    assert staff.get(INC).status_code == 403
    assert client_for().post(
        INC, {"title": "x", "description": "y"}, format="json"
    ).status_code in (
        401,
        403,
    )
    incident = SecurityIncident.objects.get()
    assert incident.notifications.get().kind == IncidentNotification.Kind.CERT_IN
    message = Notification.objects.get(template="compliance.incident_reported")
    assert admin_user.email in message.recipients
    assert "Left on a train" not in mail.outbox[-1].body  # no details in email
    assert AuditEvent.objects.filter(action=AuditAction.COMPLIANCE_INCIDENT_REPORTED).exists()


@pytest.mark.django_db
def test_people_count_moves_pending_deadlines_and_closing_has_rules(
    client_for, admin_user, organization
):
    _country(organization, "US")
    client = client_for(admin_user)
    client.post(
        INC,
        {"title": "Stolen disk", "description": "d", "personal_data_affected": True},
        format="json",
    )
    incident = SecurityIncident.objects.get()
    url = f"{INC}{incident.pk}/"
    updated = client.patch(
        url, {"version": incident.version, "people_affected": 800}, format="json"
    ).json()
    kinds = {row["kind"] for row in updated["notifications"]}
    assert kinds == {"hipaa_individuals", "hipaa_hhs", "hipaa_media"}

    version = updated["version"]
    no_summary = client.patch(url, {"version": version, "status": "closed"}, format="json")
    assert no_summary.json()["code"] == "SUMMARY_REQUIRED"
    pending = client.patch(
        url, {"version": version, "status": "closed", "closure_summary": "Done"}, format="json"
    )
    assert pending.json()["code"] == "NOTIFICATIONS_PENDING"

    rows = updated["notifications"]
    no_reason = client.post(
        f"{url}notifications/{rows[0]['id']}/", {"status": "not_required"}, format="json"
    )
    assert no_reason.json()["code"] == "REASON_REQUIRED"
    for row in rows:
        recorded = client.post(
            f"{url}notifications/{row['id']}/",
            {"status": "done", "reference": "ACK-1"},
            format="json",
        )
        assert recorded.status_code == 200
    again = client.post(f"{url}notifications/{rows[0]['id']}/", {"status": "done"}, format="json")
    assert again.json()["code"] == "ALREADY_RECORDED"
    closed = client.patch(
        url, {"version": version, "status": "closed", "closure_summary": "Done"}, format="json"
    )
    assert closed.status_code == 200 and closed.json()["closed_at"]
    reopened = client.patch(
        url, {"version": closed.json()["version"], "status": "reported"}, format="json"
    )
    assert reopened.json()["code"] == "CLOSED"


@pytest.mark.django_db
def test_deadline_alerts_are_sent_once(admin_user, organization):
    _country(organization, "IN")
    incident = SecurityIncident.objects.create(
        title="t", description="d", detected_at=timezone.now()
    )
    row = IncidentNotification.objects.create(
        incident=incident,
        kind=IncidentNotification.Kind.CERT_IN,
        due_at=timezone.now() + timedelta(hours=2),
    )
    assert send_deadline_alerts() == 1
    assert "due within 24 hours" in mail.outbox[-1].subject
    assert send_deadline_alerts() == 0
    assert send_deadline_alerts(now=row.due_at + timedelta(minutes=1)) == 1
    assert "overdue" in mail.outbox[-1].subject
    assert send_deadline_alerts(now=row.due_at + timedelta(hours=2)) == 0


@pytest.mark.django_db
def test_summary_and_permissions(client_for, admin_user, auditor_user, make_user, organization):
    _country(organization, "IN")
    assert client_for(make_user()).get("/api/v1/compliance-summary/").status_code == 403
    auditor = client_for(auditor_user)
    summary = auditor.get("/api/v1/compliance-summary/").json()
    assert summary["country"] == "IN" and summary["requirements_total"] > 10
    assert summary["risks_open"] >= len(catalog.RISKS)
    item = ComplianceRequirement.objects.first()
    assert (
        auditor.patch(f"{REQ}{item.pk}/", {"version": 1, "owner": "x"}, format="json").status_code
        == 403
    )
    assert RiskEntry.objects.count() >= len(catalog.RISKS)


@pytest.mark.django_db
def test_admin_console_updates_through_the_same_rules(admin_user, organization):
    _country(organization, "IN")
    console = Client()
    console.force_login(admin_user)
    item = ComplianceRequirement.objects.get(code="CERTIN-REPORTING")
    url = f"/admin/compliance/compliancerequirement/{item.pk}/change/"
    assert console.get(url).status_code == 200
    refused = console.post(
        url, {"status": "verified", "owner": "", "evidence": "", "next_review_on": ""}
    )
    assert refused.status_code == 200
    assert b"Say where the proof is" in refused.content
    console.post(
        url, {"status": "verified", "owner": "R", "evidence": "Report", "next_review_on": ""}
    )
    item.refresh_from_db()
    assert item.status == "verified" and item.reviewed_by == admin_user

    add = console.post(
        "/admin/compliance/securityincident/add/",
        {
            "title": "From the console",
            "description": "d",
            "severity": "low",
            "people_affected": "",
            "notifications-TOTAL_FORMS": "0",
            "notifications-INITIAL_FORMS": "0",
        },
    )
    assert add.status_code == 302, add.content[:1500]
    incident = SecurityIncident.objects.get(title="From the console")
    assert incident.reported_by == admin_user and incident.notifications.count() == 1
    console.post(
        "/admin/compliance/incidentnotification/",
        {"action": "mark_done", "_selected_action": [str(incident.notifications.get().pk)]},
    )
    assert incident.notifications.get().status == "done"
