"""API contracts and requirements traceability (spec 25.3, 25.4, 29; HIMS-DOC-001)."""

import re

import pytest
from django.test import Client
from django.urls import resolve

from apps.access_control.catalog import PERMISSIONS
from common.contracts import catalog, generator, inventory, reach
from common.contracts.inventory import SIGNED_IN

# Spec 25.4: the fields every requirement record has.
RECORD_FIELDS = (
    "ID and title",
    "Business/clinical reason",
    "Actors",
    "Preconditions",
    "Main success path",
    "Alternate/failure paths",
    "Data effects",
    "Security classification",
    "Audit requirement",
    "Idempotency/concurrency",
    "Integration dependencies",
    "Acceptance criteria",
    "Test evidence",
    "Release risk",
)


def _endpoint(method, path):
    return next(e for e in inventory.endpoints() if e.method == method and e.path == path)


def test_contract_documents_are_up_to_date():
    stale = generator.stale_files(generator.render())
    assert not stale, (
        f"Out of date: {[path.name for path in stale]}. Run `python manage.py api_contracts`."
    )


def test_every_api_view_traces_to_a_requirement():
    views = {endpoint.view_name for endpoint in inventory.endpoints()}
    missing = sorted(view for view in views if view not in catalog.VIEW_REQUIREMENTS)
    assert not missing, f"Add to common/contracts/catalog.VIEW_REQUIREMENTS: {missing}"
    unknown_views = sorted(set(catalog.VIEW_REQUIREMENTS) - views)
    assert not unknown_views, f"No longer API views; remove from the catalog: {unknown_views}"
    backlog = generator.backlog()
    unknown = sorted(
        {ticket for tickets in catalog.VIEW_REQUIREMENTS.values() for ticket in tickets}
        - set(backlog)
    )
    assert not unknown, f"Not in the Phase 1 backlog: {unknown}"


def test_every_endpoint_says_what_it_is_for():
    keys = {endpoint.key for endpoint in inventory.endpoints()}
    assert not set(catalog.PURPOSES) - keys, "PURPOSES names an endpoint that does not exist"
    vague = [endpoint.key for endpoint in inventory.endpoints() if not endpoint.summary]
    assert not vague, f"Add a docstring or a PURPOSES entry for: {vague}"


def test_every_permission_endpoint_names_a_real_permission():
    """Default deny: an action without a mapped permission could never be called by anyone."""
    broken = [
        endpoint.key
        for endpoint in inventory.endpoints()
        if endpoint.needs_permission and endpoint.permission not in PERMISSIONS
    ]
    assert not broken


def test_open_endpoints_are_only_the_expected_ones():
    """Spec 29.1: authentication at every endpoint. Anything new without sign-in must be added
    here on purpose (and reviewed)."""
    public = {e.key for e in inventory.endpoints() if e.access == inventory.PUBLIC}
    assert public == {
        "GET /api/v1/auth/csrf/",
        "POST /api/v1/auth/login/",
        "POST /api/v1/auth/login/verify/",
        "POST /api/v1/auth/login/passkey-options/",
        "POST /api/v1/auth/login/passkey/",
        "POST /api/v1/auth/invitations/inspect/",
        "POST /api/v1/auth/invitations/accept/",
        "POST /api/v1/auth/password-reset/request/",
        "POST /api/v1/auth/password-reset/inspect/",
        "POST /api/v1/auth/password-reset/confirm/",
        "GET /api/v1/features/effective/",
        "POST /api/v1/security/browser-reports/",
    }
    for key in public:
        method, path = key.split(" ")
        assert _endpoint(method, path).throttles, f"{key} has no rate limit"


def test_code_walk_finds_what_the_important_writes_record():
    """If the walk breaks, the contracts would quietly lose their audit events: pin a few."""
    facility = _endpoint("POST", "/api/v1/facilities/")
    assert facility.idempotency == "optional"
    assert facility.idempotency_operation == "facilities.create"
    assert reach.for_endpoint(facility).audit_actions == ("facility.created",)
    bed = reach.for_endpoint(_endpoint("POST", "/api/v1/beds/{pk}/status/"))
    assert "bed.status.changed" in bed.audit_actions
    assert "bed.status.changed" in bed.events
    assert bed.row_lock and bed.transaction
    assert ("STALE_RESOURCE", 409) in bed.statuses
    login = reach.for_endpoint(_endpoint("POST", "/api/v1/auth/login/"))
    assert {"auth.login", "auth.login_failed"} <= set(login.audit_actions)
    upload = reach.for_endpoint(_endpoint("POST", "/api/v1/staff/{pk}/documents/"))
    assert any(label.startswith("Virus scanner") for label in upload.external)
    removal = _endpoint("POST", "/api/v1/auth/passkeys/{passkey_id}/remove/")
    assert removal.access == SIGNED_IN
    assert _endpoint("POST", "/api/v1/role-assignments/").confirm_identity


def test_every_endpoint_resolves_to_its_view():
    for endpoint in inventory.endpoints():
        concrete = re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000001", endpoint.path)
        if "{key}" in endpoint.path or "{category}" in endpoint.path:
            concrete = re.sub(r"\{(key|category)\}", "staff", endpoint.path)
        assert resolve(concrete).func.cls is endpoint.view, endpoint.key


def _records() -> dict[str, str]:
    text = {}
    for path in sorted(generator.REQUIREMENTS.glob("*.md")):
        if path.name in {"README.md", generator.TRACEABILITY.name}:
            continue
        parts = re.split(
            r"^### (HIMS-[A-Z]+-\d{3})\s*$", path.read_text(encoding="utf-8"), flags=re.M
        )
        for ticket, body in zip(parts[1::2], parts[2::2], strict=True):
            assert ticket not in text, f"{ticket} has two records"
            text[ticket] = body.split("\n## ", 1)[0]
    return text


def test_every_done_requirement_has_a_complete_record():
    """Spec 25.4: every requirement has a record with all fourteen fields filled in."""
    records = _records()
    backlog = generator.backlog()
    done = {ticket for ticket, (_, status) in backlog.items() if generator.is_done(status)}
    assert not done - set(records), f"Write requirement records for: {sorted(done - set(records))}"
    assert not set(records) - set(backlog), "A record names a ticket the backlog does not have"
    for ticket, body in records.items():
        rows = dict(re.findall(r"^\| ([^|]+?) \| (.+?) \|\s*$", body, flags=re.M))
        for field in RECORD_FIELDS:
            assert rows.get(field, "").strip(" —-"), f"{ticket}: '{field}' is empty"
        assert rows["ID and title"].startswith(ticket), ticket


def test_records_name_only_real_events_tables_permissions_and_tests():
    """Records are written by hand: every audit event, table, permission and test file they name
    must exist, so they cannot quietly drift from the code."""
    from django.apps import apps

    from apps.audit.services import AuditAction

    actions = {value for name, value in vars(AuditAction).items() if name.isupper()}
    tables = {model._meta.db_table for model in apps.get_models()}
    root = generator.ROOT
    for ticket, body in _records().items():
        rows = dict(re.findall(r"^\| ([^|]+?) \| (.+?) \|\s*$", body, flags=re.M))
        for name in re.findall(r"`([a-z_]+(?:\.[a-z_]+)+)`", rows["Audit requirement"]):
            assert name in actions, f"{ticket}: audit event {name} does not exist"
        for name in re.findall(r"`([a-z_]+)`", rows["Data effects"]):
            assert name in tables, f"{ticket}: table {name} does not exist"
        for name in re.findall(r"`([a-z_]+(?:\.[a-z_]+)+)`", rows["Actors"]):
            assert name in PERMISSIONS, f"{ticket}: permission {name} does not exist"
        for name in re.findall(
            r"`((?:apps|common|frontend|docs)/[\w./-]+)`", rows["Test evidence"]
        ):
            path = root / name if name.startswith(("frontend", "docs")) else root / "backend" / name
            assert path.exists(), f"{ticket}: {name} does not exist"


def test_record_links_point_at_files_that_exist():
    root = generator.ROOT
    for path in generator.REQUIREMENTS.glob("*.md"):
        for target in re.findall(
            r"\]\(([^)#]+\.(?:md|py|ts|tsx|yml))(?:#[^)]*)?\)", path.read_text(encoding="utf-8")
        ):
            if target.startswith("http"):
                continue
            assert (path.parent / target).resolve().exists() or (root / target).exists(), (
                f"{path.name}: {target}"
            )


@pytest.mark.django_db
def test_api_endpoints_list_needs_roles_view(client_for, admin_user, auditor_user):
    assert client_for(auditor_user).get("/api/v1/api-endpoints/").status_code == 403
    response = client_for(admin_user).get("/api/v1/api-endpoints/")
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total"] == len(body["endpoints"]) == len(inventory.endpoints())
    row = next(
        r for r in body["endpoints"] if r["path"] == "/api/v1/facilities/" and r["method"] == "POST"
    )
    assert row["permission"] == "facilities.manage"
    assert "Organization administrator" in row["roles"]
    assert row["audit_actions"] == ["facility.created"]
    assert row["requirements"] == ["HIMS-FAC-001", "HIMS-FAC-003", "HIMS-FAC-006"]


@pytest.mark.django_db
def test_console_api_endpoints_page(admin_user, auditor_user):
    console = Client()
    console.force_login(admin_user)
    assert b'href="/admin/api-endpoints/"' in console.get("/admin/").content
    page = console.get("/admin/api-endpoints/?access=public")
    assert page.status_code == 200
    text = page.content.decode()
    assert "/api/v1/auth/login/" in text
    assert "/api/v1/facilities/" not in text
    # Auditors enter the console for the audit log but cannot see what each permission opens.
    auditor = Client()
    auditor.force_login(auditor_user)
    assert b"api-endpoints" not in auditor.get("/admin/").content
    assert auditor.get("/admin/api-endpoints/").status_code == 403
