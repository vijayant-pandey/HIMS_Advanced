""" "Today" is the hospital's, not UTC's (HIMS-STAFF-011). All data is synthetic.

The clock is set to 20:00 UTC on 6 Nov 2026: already 01:30 on 7 Nov in India (the test hospital's
time zone), and still 15:00 on 6 Nov in New York.
"""

import ast
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.access_control.delegations import _period
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.facilities.models import Facility
from apps.organizations.dates import hospital_date, hospital_today
from apps.staff import expiry
from apps.staff.models import Designation, StaffCredential, StaffDepartmentAssignment, StaffMember
from apps.staff.services import end_department_assignment

API = "/api/v1"
ROOT = Path(__file__).resolve().parents[4]
EVENING_UTC = datetime(2026, 11, 6, 20, 0, tzinfo=UTC)


@pytest.fixture
def evening_utc(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: EVENING_UTC)
    return EVENING_UTC


@pytest.fixture
def nurse(organization, make_user):
    return StaffMember.objects.create(
        organization=organization,
        user=make_user(email="nurse.dates@synthetic.test", display_name="Nurse Dates"),
        employee_number="EMP-DATE-1",
        given_name="Asha",
        family_name="Dates",
        staff_type="nurse",
        joined_on="2026-01-05",
    )


@pytest.mark.django_db
def test_today_is_the_hospitals_and_a_facility_can_have_its_own(
    organization, facility_a, evening_utc
):
    assert hospital_today() == date(2026, 11, 7)  # India
    assert hospital_today(facility_a) == date(2026, 11, 7)
    facility_a.timezone = "America/New_York"
    assert hospital_today(facility_a) == date(2026, 11, 6)
    assert hospital_date(datetime(2026, 11, 6, 18, 29, tzinfo=UTC)) == date(2026, 11, 6)
    assert hospital_date(datetime(2026, 11, 6, 18, 30, tzinfo=UTC)) == date(2026, 11, 7)


@pytest.mark.django_db
def test_before_the_hospital_is_set_up_utc_is_used(evening_utc):
    assert hospital_today() == date(2026, 11, 6)


@pytest.mark.django_db
def test_licence_that_ended_yesterday_in_india_is_expired_not_expiring(
    client_for, make_user, system_roles, nurse, evening_utc
):
    """The bug: until 5:30 am in India this licence showed as "expiring soon", 0 days left."""
    # Access is granted on the frozen clock: a grant made on the real clock would start "later".
    admin_user = make_user(role=system_roles["organization-administrator"])
    StaffCredential.objects.create(
        organization_id=nurse.organization_id,
        staff=nurse,
        credential_type="nursing_registration",
        registration_number="KNC-DATE-1",
        issuing_authority="Karnataka Nursing Council",
        jurisdiction="IN-KA",
        expires_at=date(2026, 11, 6),
    )
    client = client_for(admin_user)
    [row] = client.get(f"{API}/staff-credentials/expiring/").json()
    assert row["expiry_state"] == "expired" and row["days_left"] == -1
    assert client.get(f"{API}/staff/{nurse.pk}/").json()["credentials"][0]["expiry_state"] == (
        "expired"
    )
    future_only = {"include_expired": "false"}
    assert client.get(f"{API}/staff-credentials/expiring/", future_only).json() == []
    expiry.send_credential_expiry_alerts()
    assert nurse.credentials.get().expiry_alerts.get().days_before == 0  # the "expired" notice


@pytest.mark.django_db
def test_ending_a_posting_uses_the_day_at_its_facility(
    admin_user, nurse, department_a, monkeypatch
):
    Facility.objects.filter(pk=department_a.facility_id).update(timezone="America/New_York")
    monkeypatch.setattr(timezone, "now", lambda: datetime(2026, 11, 7, 2, 0, tzinfo=UTC))
    posting = StaffDepartmentAssignment.objects.create(
        organization_id=nurse.organization_id,
        staff=nurse,
        department=department_a,
        designation=Designation.objects.first(),
        valid_from=date(2026, 1, 5),
    )
    ended = end_department_assignment(actor=admin_user, staff=nurse, assignment_id=posting.pk)
    assert ended.valid_until == date(2026, 11, 6)  # 9 pm on 6 Nov in New York


@pytest.mark.django_db
def test_audit_search_by_day_means_the_hospitals_day(
    client_for, make_user, system_roles, evening_utc
):
    auditor_user = make_user(role=system_roles["auditor"])  # granted on the frozen clock
    AuditEvent.objects.create(
        action=AuditAction.ACCESS_DENIED,
        resource_type="api",
        outcome=AuditEvent.Outcome.DENIED,
        request_id="ref-date-0711",
        occurred_at=EVENING_UTC,  # 01:30 on 7 Nov in India
    )
    client = client_for(auditor_user)

    def found(day: str) -> int:
        query = {"request_id": "ref-date-0711", "date_from": day, "date_to": day}
        return client.get(f"{API}/audit-events/", query).json()["count"]

    assert found("2026-11-07") == 1
    assert found("2026-11-06") == 0


@pytest.mark.django_db
def test_times_in_emails_are_on_the_hospitals_clock_and_name_the_zone(organization):
    cover = SimpleNamespace(
        starts_at=datetime(2026, 11, 6, 20, 0, tzinfo=UTC),
        ends_at=datetime(2026, 11, 8, 20, 0, tzinfo=UTC),
    )
    assert _period(cover) == "from 07 Nov 2026 01:30 to 09 Nov 2026 01:30 IST"


UTC_CLOCK = {
    ("timezone", "localdate"),
    ("timezone", "localtime"),
    ("timezone", "get_current_timezone"),
    ("date", "today"),
    ("datetime", "today"),
}


def test_nothing_works_out_today_on_the_utc_clock():
    """Use apps.organizations.dates; in the screens, components/dates.ts."""
    allowed = {ROOT / "backend" / "apps" / "organizations" / "dates.py"}
    for folder in ("apps", "common", "config"):
        for path in (ROOT / "backend" / folder).rglob("*.py"):
            if path in allowed or "tests" in path.parts or "migrations" in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and (node.value.id, node.attr) in UTC_CLOCK
                ):
                    pytest.fail(f"{path}:{node.lineno}: use apps.organizations.dates")
    frontend = ROOT / "frontend"
    for path in [*(frontend / "src").rglob("*.ts*"), *(frontend / "e2e").rglob("*.*s")]:
        # Folders such as e2e/.mail-us (browser-test output) match the pattern too: files only.
        if not path.is_file() or path.name == "dates.ts" or ".test." in path.name:
            continue
        if "toISOString().slice(0, 10)" in path.read_text(encoding="utf-8"):
            pytest.fail(f"{path}: use localDate from components/dates.ts")
