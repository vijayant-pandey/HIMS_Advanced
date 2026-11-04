"""What browsers blocked under the security headers (HIMS-SEC-012). Synthetic data."""

import json

import pytest
from django.test import Client, override_settings

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.compliance import browser_reports
from apps.compliance.models import BrowserSecurityReport

URL = "/api/v1/security/browser-reports/"
LIST = "/api/v1/browser-security-reports/"
STATUS = "/api/v1/security/status/"


def _send(body, content_type="application/csp-report"):
    payload = body if isinstance(body, str) else json.dumps(body)
    return Client().post(URL, data=payload, content_type=content_type)


def _report(**extra):
    return {
        "csp-report": {
            "document-uri": "https://hims.example/patients/4f1c2b7e-8d21-4c3a-9b1e-2f6a7c8d9e01/?name=Synthetic",
            "effective-directive": "script-src-elem",
            "violated-directive": "script-src-elem",
            "blocked-uri": "https://evil.example:8443/x.js?token=abc",
            "script-sample": "alert('Synthetic Patient')",
            **extra,
        }
    }


@pytest.mark.django_db
def test_report_is_stored_without_query_strings_ids_or_code_samples():
    assert _send(_report()).status_code == 204
    row = BrowserSecurityReport.objects.get()
    assert row.directive == "script-src-elem"
    assert row.blocked == "https://evil.example:8443"
    assert row.page_path == "/patients/{id}/"
    stored = json.dumps([row.directive, row.blocked, row.page_path])
    assert "Synthetic" not in stored and "token" not in stored


@pytest.mark.django_db
def test_same_block_is_added_up_per_day():
    _send(_report())
    _send(_report())
    assert BrowserSecurityReport.objects.get().occurrences == 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"csp-report": "text"},
        {"csp-report": {"effective-directive": "<script>", "blocked-uri": "inline"}},
        {"csp-report": {"blocked-uri": "inline"}},
        [1, 2],
        _report(**{"blocked-uri": "https://[bad", "document-uri": "https://[bad"}),
    ],
)
def test_nonsense_is_ignored_with_the_same_answer(body):
    assert _send(body).status_code == 204
    assert not BrowserSecurityReport.objects.exists()


@pytest.mark.django_db
def test_oversized_report_is_ignored():
    assert _send(_report(padding="x" * browser_reports.MAX_REPORT_BYTES)).status_code == 204
    assert not BrowserSecurityReport.objects.exists()


@pytest.mark.django_db
def test_reports_per_day_are_capped(monkeypatch):
    monkeypatch.setattr(browser_reports, "MAX_ROWS_PER_DAY", 2)
    for index in range(4):
        _send(_report(**{"blocked-uri": f"https://site{index}.example/x.js"}))
    assert BrowserSecurityReport.objects.count() == 2


def test_inline_and_data_blocks_keep_only_the_kind():
    assert browser_reports._blocked_site("inline") == "inline"
    assert browser_reports._blocked_site("data:text/html;base64,AAAA") == "data"


@pytest.mark.django_db
def test_auditor_reads_but_cannot_review(client_for, auditor_user):
    _send(_report())
    client = client_for(auditor_user)
    rows = client.get(LIST).json()
    assert rows[0]["blocked"] == "https://evil.example:8443"
    response = client.post(f"{LIST}{rows[0]['id']}/review/", {"version": 1}, format="json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_plain_staff_cannot_read_reports_or_status(client_for, make_user):
    client = client_for(make_user())
    assert client.get(LIST).status_code == 403
    assert client.get(STATUS).status_code == 403


@pytest.mark.django_db
def test_review_is_audited_and_only_once(client_for, admin_user):
    _send(_report())
    client = client_for(admin_user)
    row = client.get(LIST).json()[0]
    url = f"{LIST}{row['id']}/review/"
    response = client.post(
        url, {"version": row["version"], "note": "Browser add-on"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["review_note"] == "Browser add-on"
    event = AuditEvent.objects.get(action=AuditAction.COMPLIANCE_BROWSER_REPORT_REVIEWED)
    assert event.actor_id == admin_user.pk
    assert client.post(url, {"version": 1}, format="json").status_code == 409
    assert client.post(url, {"version": 2}, format="json").status_code == 409


@pytest.mark.django_db
@override_settings(HIMS_TRUSTED_PROXIES=["127.0.0.0/8"])
def test_status_shows_the_address_written_to_the_audit_log(client_for, admin_user):
    _send(_report())
    data = client_for(admin_user).get(STATUS, HTTP_X_FORWARDED_FOR="203.0.113.9").json()
    assert data == {
        "policy_mode": "enforcing",
        "proxies_configured": True,
        "your_address": "203.0.113.9",
        "reports_to_review": 1,
    }


@pytest.mark.django_db
def test_admin_console_marks_reviewed(client_for, admin_user):
    _send(_report())
    row = BrowserSecurityReport.objects.get()
    console = Client()
    console.force_login(admin_user)
    response = console.post(
        "/admin/compliance/browsersecurityreport/",
        {"action": "mark_reviewed", "_selected_action": [str(row.pk)]},
    )
    assert response.status_code in (200, 302)
    row.refresh_from_db()
    assert row.reviewed_by_id == admin_user.pk
