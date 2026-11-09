"""Console access tab, refused addresses and the console's Security status page (HIMS-SEC-015).
Synthetic data; addresses are documentation ranges."""

import pytest
from django.core.cache import cache
from django.test import Client, override_settings

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.compliance.models import ConsoleAccessBlock

STATUS = "/api/v1/security/console-access/"
LIST = "/api/v1/console-access-blocks/"
OUTSIDE = "203.0.113.9"


@pytest.fixture(autouse=True)
def _clear_lockouts():
    cache.clear()


def _refuse(address=OUTSIDE):
    Client().get("/admin/login/", REMOTE_ADDR=address)
    return ConsoleAccessBlock.objects.get(ip_address=address)


@pytest.mark.django_db
def test_status_says_where_the_console_can_be_used_from(client_for, admin_user):
    _refuse()
    assert client_for(admin_user).get(STATUS).json() == {
        "enabled": True,
        "allowed_networks": ["127.0.0.1", "::1"],
        "your_address": "127.0.0.1",
        "you_are_allowed": True,
        "developer_pc": True,
        "refusals_to_review": 1,
    }


@pytest.mark.django_db
@override_settings(HIMS_ADMIN_ALLOWED_NETWORKS=["192.0.2.0/24"])
def test_status_warns_a_person_whose_own_address_is_not_listed(client_for, admin_user):
    body = client_for(admin_user).get(STATUS).json()
    assert (body["your_address"], body["you_are_allowed"]) == ("127.0.0.1", False)


@pytest.mark.django_db
def test_refusals_are_listed_with_the_signed_in_person(client_for, admin_user):
    console = Client()
    console.force_login(admin_user)
    console.get("/admin/", REMOTE_ADDR=OUTSIDE)
    rows = client_for(admin_user).get(LIST).json()
    assert len(rows) == 1
    assert rows[0]["ip_address"] == OUTSIDE
    assert rows[0]["attempts"] == 1
    assert rows[0]["last_path"] == "/admin/"
    assert rows[0]["signed_in_user_name"] == admin_user.display_name
    assert rows[0]["reviewed_at"] is None


@pytest.mark.django_db
def test_review_is_audited_and_only_once(client_for, admin_user):
    block = _refuse()
    client = client_for(admin_user)
    url = f"{LIST}{block.pk}/review/"
    response = client.post(url, {"version": 1, "note": "Our own test"}, format="json")
    assert response.status_code == 200
    assert response.json()["review_note"] == "Our own test"
    assert response.json()["reviewed_by_name"] == admin_user.display_name
    event = AuditEvent.objects.get(action=AuditAction.COMPLIANCE_CONSOLE_BLOCK_REVIEWED)
    assert event.resource_id == str(block.pk)
    assert client.post(url, {"version": 1}, format="json").status_code == 409
    assert client.post(url, {"version": 2}, format="json").status_code == 409
    assert client.get(STATUS).json()["refusals_to_review"] == 0


@pytest.mark.django_db
def test_auditor_reads_but_cannot_review_and_others_see_nothing(
    client_for, auditor_user, make_user
):
    block = _refuse()
    auditor = client_for(auditor_user)
    assert auditor.get(LIST).status_code == 200
    assert auditor.get(STATUS).status_code == 200
    review = auditor.post(f"{LIST}{block.pk}/review/", {"version": 1}, format="json")
    assert review.status_code == 403
    nobody = client_for(make_user())
    assert nobody.get(LIST).status_code == 403
    assert nobody.get(STATUS).status_code == 403


@pytest.mark.django_db
def test_admin_console_marks_refusals_reviewed(admin_user):
    block = _refuse()
    console = Client()
    console.force_login(admin_user)
    url = "/admin/compliance/consoleaccessblock/"
    assert console.get(url).status_code == 200
    console.post(url, {"action": "mark_reviewed", "_selected_action": [str(block.pk)]})
    block.refresh_from_db()
    assert block.reviewed_by_id == admin_user.pk
    assert block.version == 2


@pytest.mark.django_db
def test_console_security_status_page(admin_user, make_user, organization):
    _refuse()
    console = Client()
    console.force_login(admin_user)
    home = console.get("/admin/")
    assert b'href="/admin/compliance/consoleaccessblock/security-status/"' in home.content
    page = console.get("/admin/compliance/consoleaccessblock/security-status/")
    assert page.status_code == 200
    text = page.content.decode()
    for expected in (
        "Admin console: where it can be used from",
        "127.0.0.1, ::1",
        "127.0.0.1 (allowed)",
        "Browser protection",
        "Database users",
        "HIMS_ADMIN_ALLOWED_NETWORKS",
    ):
        assert expected in text, expected
    # Someone in the console without compliance.view sees neither the link nor the page.
    from apps.access_control.catalog import P
    from apps.access_control.services import assign_role, create_role

    role = create_role(
        actor=None,
        organization=organization,
        code="console-only",
        name="Console only",
        permissions=[P.ADMIN_CONSOLE],
    )
    limited = make_user()
    assign_role(actor=None, user=limited, role=role)
    other = Client()
    other.force_login(limited)
    assert b"security-status" not in other.get("/admin/").content
    assert other.get("/admin/compliance/consoleaccessblock/security-status/").status_code == 403
