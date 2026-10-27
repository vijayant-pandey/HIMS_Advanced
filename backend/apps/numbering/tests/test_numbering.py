"""Hospital numbering schemes, HIMS-ORG-003. All data is synthetic."""

import threading
from datetime import date

import pytest
from django.db import connection, transaction
from django.test import override_settings

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.numbering import formatting
from apps.numbering.models import IssuedNumber, NumberingScheme
from apps.numbering.services import (
    NumberingNotConfigured,
    ensure_default_schemes,
    issue_number,
    set_next_number,
)
from common.exceptions import ConflictError

API = "/api/v1"
OCT_2026 = date(2026, 10, 27)


@pytest.fixture
def schemes(organization):
    ensure_default_schemes(organization)
    return {s.document_type: s for s in NumberingScheme.objects.filter(facility__isnull=True)}


# --- Formatting (pure) ----------------------------------------------------------------------


def fmt(**overrides):
    values = {
        "prefix": "INV",
        "separator": "/",
        "include_facility_code": False,
        "period": "financial_year",
        "year_format": "short",
        "financial_year_start_month": 4,
        "padding": 6,
        **overrides,
    }
    return formatting.Format(**values)


@pytest.mark.parametrize(
    ("overrides", "on", "expected"),
    [
        ({}, date(2026, 10, 27), "INV/26-27/000001"),
        ({}, date(2027, 3, 31), "INV/26-27/000001"),  # still FY 2026-27
        ({}, date(2027, 4, 1), "INV/27-28/000001"),  # new financial year
        ({"year_format": "full"}, date(2026, 10, 27), "INV/2026-27/000001"),
        ({"period": "calendar_year", "separator": "-"}, date(2026, 10, 27), "INV-26-000001"),
        ({"period": "month", "year_format": "full"}, date(2026, 10, 27), "INV/202610/000001"),
        ({"period": "none", "prefix": "MRN", "padding": 8}, date(2026, 10, 27), "MRN/00000001"),
        (
            {"financial_year_start_month": 1, "year_format": "full"},
            date(2026, 10, 1),
            "INV/2026/000001",
        ),
        ({"include_facility_code": True}, date(2026, 10, 27), "INV/BLR/26-27/000001"),
    ],
)
def test_number_formats(overrides, on, expected):
    f = fmt(**overrides)
    key = formatting.period_key(f, on)
    assert formatting.format_number(f, sequence=1, key=key, facility_code="blr") == expected


def test_short_and_full_year_share_one_counter():
    assert formatting.period_key(fmt(year_format="short"), OCT_2026) == formatting.period_key(
        fmt(year_format="full"), OCT_2026
    )


# --- Defaults ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_india_defaults_are_created_once_and_audited(organization, schemes):
    assert set(schemes) == {"mrn", "encounter", "invoice", "claim"}
    assert ensure_default_schemes(organization) == []  # running again changes nothing
    invoice = issue_number(document_type="invoice", on=OCT_2026)
    assert invoice.value == "INV/26-27/000001"
    assert len(invoice.value) <= 16  # GST limit
    assert issue_number(document_type="mrn", on=OCT_2026).value == "MRN-00000001"
    assert issue_number(document_type="encounter", on=OCT_2026).value == "ENC-2026-0000001"
    assert AuditEvent.objects.filter(action=AuditAction.NUMBERING_SCHEME_CREATED).count() == 4


# --- Issuing ----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_numbers_are_sequential_and_restart_each_period(schemes):
    values = [issue_number(document_type="encounter", on=OCT_2026).value for _ in range(3)]
    assert values == ["ENC-2026-0000001", "ENC-2026-0000002", "ENC-2026-0000003"]
    assert issue_number(document_type="encounter", on=date(2027, 1, 1)).value == "ENC-2027-0000001"


@pytest.mark.django_db
def test_rolled_back_record_gives_its_number_back(schemes):
    with pytest.raises(RuntimeError), transaction.atomic():
        issue_number(document_type="invoice", on=OCT_2026)
        raise RuntimeError("invoice could not be saved")
    # No gap: the next invoice still gets 000001 (GST series must be continuous).
    assert issue_number(document_type="invoice", on=OCT_2026).value == "INV/26-27/000001"


@pytest.mark.django_db
def test_facility_scheme_overrides_hospital_wide_except_mrn(schemes, facility_a, facility_b):
    NumberingScheme.objects.create(
        organization_id=facility_a.organization_id,
        document_type="encounter",
        facility=facility_a,
        prefix="OP",
        include_facility_code=True,
        period="none",
        padding=5,
    )
    assert issue_number(document_type="encounter", facility=facility_a).value == "OP-FAC-A-00001"
    assert issue_number(document_type="encounter", facility=facility_b, on=OCT_2026).value == (
        "ENC-2026-0000001"
    )
    mrn = NumberingScheme(document_type="mrn", facility=facility_a, padding=6)
    with pytest.raises(Exception, match="hospital-wide"):
        mrn.full_clean()


@pytest.mark.django_db
def test_format_change_never_reuses_a_number(schemes):
    mrn = schemes["mrn"]
    assert issue_number(document_type="mrn").value == "MRN-00000001"
    mrn.prefix = "PAT"
    mrn.save()
    assert issue_number(document_type="mrn").value == "PAT-00000002"
    mrn.prefix = "MRN"
    mrn.save()
    assert issue_number(document_type="mrn").value == "MRN-00000003"
    assert IssuedNumber.objects.count() == 3


@pytest.mark.django_db
def test_inactive_scheme_means_not_configured(schemes):
    NumberingScheme.objects.filter(document_type="claim").update(is_active=False)
    with pytest.raises(NumberingNotConfigured):
        issue_number(document_type="claim")


@pytest.mark.django_db
def test_continue_from_previous_system_only_moves_forward(schemes, admin_user):
    mrn = schemes["mrn"]
    set_next_number(actor=admin_user, scheme_id=mrn.pk, version=1, next_value=54322)
    assert issue_number(document_type="mrn").value == "MRN-00054322"
    with pytest.raises(ConflictError, match="only move forward"):
        set_next_number(actor=admin_user, scheme_id=mrn.pk, version=2, next_value=100)
    event = AuditEvent.objects.get(action=AuditAction.NUMBERING_NEXT_NUMBER_SET)
    assert event.changes == {"before": {"next": 1}, "after": {"next": 54322}}


@pytest.mark.django_db
def test_gst_length_limit_is_enforced_for_india_invoices(schemes):
    invoice = schemes["invoice"]
    invoice.year_format = "full"  # INV/2026-27/000001 = 18 characters
    with pytest.raises(Exception, match="at most 16"):
        invoice.full_clean()


@pytest.mark.django_db(transaction=True)
def test_simultaneous_requests_never_get_the_same_number(organization):
    ensure_default_schemes(organization)
    results, errors = [], []

    def worker():
        try:
            for _ in range(5):
                results.append(issue_number(document_type="mrn").value)
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len(results) == 30
    assert len(set(results)) == 30  # no duplicates
    assert sorted(results) == [f"MRN-{n:08d}" for n in range(1, 31)]  # no gaps


# --- API --------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_lists_and_edits_schemes_with_audit(client_for, admin_user, schemes):
    client = client_for(admin_user)
    listing = client.get(f"{API}/numbering-schemes/").json()
    assert {row["document_type"] for row in listing} == {"mrn", "encounter", "invoice", "claim"}
    mrn = next(row for row in listing if row["document_type"] == "mrn")
    assert mrn["next_number"] == "MRN-00000001"
    assert mrn["facility_name"] is None

    url = f"{API}/numbering-schemes/{mrn['id']}/"
    changed = client.patch(url, {"version": 1, "prefix": "UHID", "padding": 6}, format="json")
    assert changed.status_code == 200
    assert changed.json()["next_number"] == "UHID-000001"
    assert client.patch(url, {"version": 1, "prefix": "X"}, format="json").status_code == 409
    event = AuditEvent.objects.get(action=AuditAction.NUMBERING_SCHEME_UPDATED)
    assert event.changes["after"] == {"prefix": "UHID", "padding": 6}


@pytest.mark.django_db
def test_preview_shows_example_and_problems_without_saving(client_for, admin_user, schemes):
    client = client_for(admin_user)
    body = {
        "document_type": "invoice",
        "prefix": "INVOICE",
        "separator": "/",
        "period": "financial_year",
        "year_format": "full",
        "padding": 6,
    }
    response = client.post(f"{API}/numbering-schemes/preview/", body, format="json")
    assert response.status_code == 200
    data = response.json()
    assert data["example"].startswith("INVOICE/")
    assert "padding" in data["errors"]  # too long for GST
    assert NumberingScheme.objects.count() == 4  # nothing saved


@pytest.mark.django_db
def test_continue_numbering_endpoint(client_for, admin_user, schemes):
    client = client_for(admin_user)
    url = f"{API}/numbering-schemes/{schemes['mrn'].pk}/next-number/"
    ok = client.post(url, {"version": 1, "next_value": 1001}, format="json")
    assert ok.status_code == 200
    assert ok.json()["next_number"] == "MRN-00001001"
    back = client.post(url, {"version": 2, "next_value": 5}, format="json")
    assert back.status_code == 409
    assert back.json()["code"] == "NUMBER_WOULD_GO_BACKWARDS"


@pytest.mark.django_db
def test_facility_admin_manages_only_own_facility_series(
    client_for, make_user, system_roles, schemes, facility_a, facility_b
):
    client = client_for(make_user(role=system_roles["facility-administrator"], facility=facility_a))
    body = {"document_type": "encounter", "prefix": "OPD", "period": "none", "padding": 5}
    own = client.post(
        f"{API}/numbering-schemes/", {**body, "facility": str(facility_a.pk)}, format="json"
    )
    assert own.status_code == 201, own.json().get("errors")
    other = client.post(
        f"{API}/numbering-schemes/", {**body, "facility": str(facility_b.pk)}, format="json"
    )
    assert other.status_code == 403
    hospital_wide = client.patch(
        f"{API}/numbering-schemes/{schemes['mrn'].pk}/",
        {"version": 1, "prefix": "X"},
        format="json",
    )
    assert hospital_wide.status_code == 403
    # ...but they can see the hospital-wide rules that apply to their facility
    listing = client.get(f"{API}/numbering-schemes/").json()
    assert len(listing) == 5


@pytest.mark.django_db
def test_duplicate_scheme_is_refused(client_for, admin_user, schemes):
    response = client_for(admin_user).post(
        f"{API}/numbering-schemes/", {"document_type": "mrn", "padding": 6}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_staff_without_permission_cannot_see_numbering(
    client_for, make_user, system_roles, facility_a
):
    client = client_for(make_user(role=system_roles["basic-staff"], facility=facility_a))
    assert client.get(f"{API}/numbering-schemes/").status_code == 403
    assert client.get(f"{API}/issued-numbers/").status_code == 403


@pytest.mark.django_db
def test_issued_register_lists_numbers(client_for, admin_user, schemes):
    issue_number(document_type="mrn", actor=admin_user, reference="patient:synthetic-1")
    rows = client_for(admin_user).get(f"{API}/issued-numbers/").json()["results"]
    assert rows[0]["value"] == "MRN-00000001"
    assert rows[0]["issued_by_name"] == admin_user.display_name


@pytest.mark.django_db
def test_changing_numbering_requires_two_factor(make_user, system_roles, facility_a):
    from apps.identity.mfa import is_required

    with override_settings(HIMS_MFA_REQUIRED_FOR_PRIVILEGED=True):
        user = make_user(role=system_roles["facility-administrator"], facility=facility_a)
        assert is_required(user)
