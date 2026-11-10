"""Leave balances and entitlements (HIMS-STAFF-013; spec 4.3). All data is synthetic."""

from datetime import date, timedelta

import pytest
from django.db import DatabaseError, transaction

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.organizations.dates import hospital_today
from apps.organizations.models import Organization
from apps.rosters import balances
from apps.rosters.models import LeaveBalanceAdjustment, LeaveEntitlement, LeaveRequest
from apps.staff.models import StaffMember
from common.admin.tests.test_console_additions import console

API = "/api/v1"


@pytest.fixture
def client(client_for, admin_user):
    client = client_for(admin_user)
    client.default_format = "json"
    return client


def this_year():
    return balances.current_year()


def _entitlement(leave_type="annual", from_year=None, days=20, max_carry_over=0, prorate=False):
    return LeaveEntitlement.objects.create(
        leave_type=leave_type,
        from_year=this_year() if from_year is None else from_year,
        days=days,
        max_carry_over=max_carry_over,
        prorate_on_joining=prorate,
    )


def _leave(staff, department, start, end, *, leave_type="annual", status="approved"):
    return LeaveRequest.objects.create(
        organization_id=staff.organization_id,
        staff=staff,
        facility_id=department.facility_id,
        department=department,
        leave_type=leave_type,
        start_date=start,
        end_date=end,
        status=status,
    )


def _balance(staff, leave_type="annual", year=None):
    rows = balances.balances_for([staff], year=year)[staff.pk]
    return next(b for b in rows if b.leave_type == leave_type)


def _joined(staff, day):
    StaffMember.objects.filter(pk=staff.pk).update(joined_on=day)
    staff.refresh_from_db()


def _in_year(year=None, month=6, day=1):
    return date(this_year() if year is None else year, month, day)


@pytest.mark.parametrize(
    "day,month,year",
    [
        (date(2026, 1, 1), 1, 2026),
        (date(2026, 12, 31), 1, 2026),
        (date(2026, 3, 31), 4, 2025),  # April to March: still last year's
        (date(2026, 4, 1), 4, 2026),
    ],
)
def test_which_leave_year_a_day_is_in(day, month, year):
    assert balances.leave_year_of(day, month) == year


def test_leave_year_names_and_ends():
    assert balances.year_label(2026, 1) == "2026"
    assert balances.year_label(2026, 4) == "2026-27"
    assert balances.year_bounds(2026, 4) == (date(2026, 4, 1), date(2027, 3, 31))
    assert balances.year_bounds(2024, 3)[1] == date(2025, 2, 28)


@pytest.mark.django_db
def test_no_entitlement_means_no_balance_and_nothing_changes(
    client,
    organization,
    department_a,
    person,
):
    staff = person(department_a)
    assert balances.balances_for([staff])[staff.pk] == []
    leave = _leave(staff, department_a, _in_year(), _in_year(), status="requested")
    assert balances.balance_after(leave) is None


@pytest.mark.django_db
def test_balance_counts_approved_leave_and_shows_waiting_apart(
    organization,
    department_a,
    person,
):
    _entitlement(days=20)
    staff = person(department_a)
    _joined(staff, date(this_year() - 1, 1, 1))
    _leave(staff, department_a, _in_year(month=2), _in_year(month=2, day=3))  # 3 days
    _leave(staff, department_a, _in_year(month=3), _in_year(month=3, day=2), status="requested")
    _leave(staff, department_a, _in_year(month=4), _in_year(month=4, day=5), status="cancelled")
    _leave(staff, department_a, _in_year(month=5), _in_year(month=5, day=5), status="rejected")
    _leave(
        staff, department_a, _in_year(month=6), _in_year(month=6, day=2), leave_type="sick"
    )  # another kind
    balance = _balance(staff)
    assert (balance.entitled, balance.taken, balance.waiting, balance.remaining) == (20, 3, 2, 17)


@pytest.mark.django_db
def test_unused_days_carry_over_up_to_the_limit(organization, department_a, person):
    year = this_year()
    # The row must start in the past for this test, so it is written directly.
    _entitlement(from_year=year - 2, days=10, max_carry_over=4)
    staff = person(department_a)
    _joined(staff, date(year - 3, 1, 1))
    _leave(staff, department_a, date(year - 2, 2, 1), date(year - 2, 2, 8))  # 8 of 10: 2 left
    _leave(staff, department_a, date(year - 1, 2, 1), date(year - 1, 2, 2))  # 2 of 12: 10 left
    assert _balance(staff, year=year - 2).remaining == 2
    last = _balance(staff, year=year - 1)
    assert (last.carried_in, last.remaining) == (2, 10)
    now = _balance(staff, year=year)
    assert (now.carried_in, now.entitled, now.remaining) == (4, 10, 14)  # 4 is the limit


@pytest.mark.django_db
def test_overspending_does_not_carry_a_debt_or_a_credit(
    organization,
    department_a,
    person,
):
    year = this_year()
    _entitlement(from_year=year - 1, days=2, max_carry_over=5)
    staff = person(department_a)
    _joined(staff, date(year - 2, 1, 1))
    _leave(staff, department_a, date(year - 1, 2, 1), date(year - 1, 2, 5))
    assert _balance(staff, year=year - 1).remaining == -3
    assert _balance(staff, year=year).carried_in == 0


@pytest.mark.django_db
def test_a_later_entitlement_replaces_an_earlier_one_from_its_year(
    organization,
    department_a,
    person,
):
    year = this_year()
    _entitlement(from_year=year - 1, days=10, max_carry_over=0)
    _entitlement(from_year=year, days=25, max_carry_over=0)
    staff = person(department_a)
    _joined(staff, date(year - 2, 1, 1))
    assert _balance(staff, year=year - 1).entitled == 10
    assert _balance(staff, year=year).entitled == 25


@pytest.mark.django_db
def test_tracking_can_be_switched_off_from_a_year(
    organization,
    department_a,
    person,
):
    year = this_year()
    _entitlement(from_year=year - 1, days=10, max_carry_over=5)
    off = _entitlement(from_year=year, days=0)
    LeaveEntitlement.objects.filter(pk=off.pk).update(tracked=False)
    staff = person(department_a)
    _joined(staff, date(year - 2, 1, 1))
    assert balances.balances_for([staff], year=year)[staff.pk] == []
    assert _balance(staff, year=year - 1).entitled == 10


@pytest.mark.django_db
def test_joining_during_the_year_gives_a_share_by_whole_months(
    organization,
    department_a,
    person,
):
    Organization.objects.update(leave_year_start_month=1)
    year = this_year()
    _entitlement(from_year=year, days=24, prorate=True)
    staff = person(department_a)
    _joined(staff, date(year, 10, 15))  # October, November, December: 3 of 12
    assert _balance(staff, year=year).entitled == 6
    _joined(staff, date(year, 1, 1))
    assert _balance(staff, year=year).entitled == 24
    LeaveEntitlement.objects.update(prorate_on_joining=False)
    _joined(staff, date(year, 10, 15))
    assert _balance(staff, year=year).entitled == 24


@pytest.mark.django_db
def test_someone_who_has_not_joined_yet_has_no_balance(
    organization,
    department_a,
    person,
):
    year = this_year()
    _entitlement(from_year=year - 1)
    staff = person(department_a)
    _joined(staff, date(year, 1, 1))
    assert balances.balances_for([staff], year=year - 2)[staff.pk] == []


@pytest.mark.django_db
def test_leave_across_two_leave_years_counts_in_each(
    organization,
    department_a,
    person,
):
    Organization.objects.update(leave_year_start_month=1)
    year = this_year()
    _entitlement(from_year=year - 1, days=10)
    staff = person(department_a)
    _joined(staff, date(year - 2, 1, 1))
    _leave(staff, department_a, date(year - 1, 12, 30), date(year, 1, 2))  # 2 days and 2 days
    assert _balance(staff, year=year - 1).taken == 2
    assert _balance(staff, year=year).taken == 2


@pytest.mark.django_db
def test_the_leave_year_can_start_in_april(organization, department_a, person):
    Organization.objects.update(leave_year_start_month=4)
    year = this_year()
    _entitlement(from_year=year, days=10)
    staff = person(department_a)
    _joined(staff, date(year - 1, 1, 1))
    _leave(staff, department_a, date(year, 4, 1), date(year, 4, 2))
    _leave(staff, department_a, date(year, 3, 1), date(year, 3, 2))  # last leave year
    balance = _balance(staff, year=year)
    assert balance.taken == 2 and balance.year_label == f"{year}-{str(year + 1)[-2:]}"


@pytest.mark.django_db
def test_approving_over_the_balance_needs_a_decision_and_a_reason(
    client,
    organization,
    department_a,
    person,
):
    _entitlement(days=1)
    staff = person(department_a)
    _joined(staff, date(this_year() - 1, 1, 1))
    start = hospital_today() + timedelta(days=5)
    leave = _leave(staff, department_a, start, start + timedelta(days=1), status="requested")
    listed = client.get(f"{API}/leave-requests/{leave.pk}/").json()
    assert listed["balance_after"] == -1
    url = f"{API}/leave-requests/{leave.pk}/approve/"
    refused = client.post(url, {"version": leave.version})
    assert refused.status_code == 409 and refused.json()["code"] == "LEAVE_OVER_BALANCE"
    no_reason = client.post(url, {"version": leave.version, "allow_over_balance": True})
    assert no_reason.json()["code"] == "REASON_REQUIRED"
    approved = client.post(
        url, {"version": leave.version, "allow_over_balance": True, "note": "Family emergency"}
    )
    assert approved.status_code == 200, approved.content
    event = AuditEvent.objects.get(action=AuditAction.LEAVE_APPROVED)
    assert event.metadata["over_balance_by"] == 1
    assert _balance(staff).remaining == -1
    assert client.get(f"{API}/leave-requests/{leave.pk}/").json()["balance_after"] is None


@pytest.mark.django_db
def test_approving_within_the_balance_works_as_before(
    client,
    organization,
    department_a,
    person,
):
    _entitlement(days=10)
    staff = person(department_a)
    _joined(staff, date(this_year() - 1, 1, 1))
    start = hospital_today() + timedelta(days=5)
    leave = _leave(staff, department_a, start, start, status="requested")
    response = client.post(f"{API}/leave-requests/{leave.pk}/approve/", {"version": leave.version})
    assert response.status_code == 200, response.content
    assert "over_balance_by" not in (
        AuditEvent.objects.get(action=AuditAction.LEAVE_APPROVED).metadata or {}
    )


@pytest.mark.django_db
def test_setting_entitlements_past_rows_stay_as_they_were(client, organization):
    year = this_year()
    past = client.post(
        f"{API}/leave-entitlements/", {"leave_type": "annual", "from_year": year - 1, "days": 20}
    )
    assert past.status_code == 409 and past.json()["code"] == "PAST_YEAR"
    added = client.post(
        f"{API}/leave-entitlements/",
        {"leave_type": "annual", "from_year": year, "days": 20, "max_carry_over": 5},
    )
    assert added.status_code == 201, added.content
    body = added.json()
    assert body["can_change"] is True and body["leave_type_label"].startswith("Annual")
    twice = client.post(
        f"{API}/leave-entitlements/", {"leave_type": "annual", "from_year": year, "days": 25}
    )
    assert twice.status_code == 409
    changed = client.patch(
        f"{API}/leave-entitlements/{body['id']}/", {"version": body["version"], "days": 22}
    )
    assert changed.json()["days"] == 22
    assert AuditEvent.objects.filter(action=AuditAction.LEAVE_ENTITLEMENT_UPDATED).count() == 1
    old = _entitlement(leave_type="sick", from_year=year - 1, days=5)
    refused = client.patch(f"{API}/leave-entitlements/{old.pk}/", {"version": 1, "days": 6})
    assert refused.status_code == 409 and refused.json()["code"] == "ENTITLEMENT_IN_USE"


@pytest.mark.django_db
def test_adjusting_a_balance_has_a_reason_and_cannot_be_changed(
    client,
    organization,
    department_a,
    person,
):
    _entitlement(days=10)
    staff = person(department_a)
    _joined(staff, date(this_year() - 1, 1, 1))
    body = {"staff": str(staff.pk), "leave_type": "annual", "leave_year": this_year(), "days": 3}
    assert client.post(f"{API}/leave-adjustments/", {**body, "reason": " "}).status_code == 400
    added = client.post(f"{API}/leave-adjustments/", {**body, "reason": "Brought from old system"})
    assert added.status_code == 201, added.content
    assert _balance(staff).remaining == 13 and _balance(staff).adjusted == 3
    client.post(f"{API}/leave-adjustments/", {**body, "days": -1, "reason": "Correction"})
    assert _balance(staff).remaining == 12
    listed = client.get(f"{API}/leave-adjustments/?person={staff.pk}").json()
    assert {row["days"] for row in listed} == {3, -1}
    assert AuditEvent.objects.filter(action=AuditAction.LEAVE_BALANCE_ADJUSTED).count() == 2
    row = LeaveBalanceAdjustment.objects.first()
    with pytest.raises(DatabaseError), transaction.atomic():
        LeaveBalanceAdjustment.objects.filter(pk=row.pk).update(days=9)
    with pytest.raises(DatabaseError), transaction.atomic():
        LeaveBalanceAdjustment.objects.filter(pk=row.pk).delete()


@pytest.mark.django_db
def test_adjusting_refuses_zero_untracked_and_your_own(
    client_for,
    admin_user,
    organization,
    department_a,
    person,
):
    client = client_for(admin_user)
    client.default_format = "json"
    _entitlement(days=10)
    staff = person(department_a)
    body = {
        "staff": str(staff.pk),
        "leave_type": "annual",
        "leave_year": this_year(),
        "days": 1,
        "reason": "x",
    }
    zero = client.post(f"{API}/leave-adjustments/", {**body, "days": 0})
    assert zero.json()["code"] == "NO_CHANGE"
    untracked = client.post(f"{API}/leave-adjustments/", {**body, "leave_type": "sick"})
    assert untracked.json()["code"] == "NOT_TRACKED"
    StaffMember.objects.filter(pk=staff.pk).update(user=admin_user)
    own = client.post(f"{API}/leave-adjustments/", body)
    assert own.json()["code"] == "SELF_ADJUST"


@pytest.mark.django_db
def test_department_balances_for_those_who_decide_leave_there(
    client_for,
    make_user,
    system_roles,
    organization,
    facility_a,
    facility_b,
    department_a,
    person,
):
    _entitlement(days=10)
    _entitlement(leave_type="sick", days=5)
    staff = person(department_a)
    _joined(staff, date(this_year() - 1, 1, 1))
    head = client_for(
        make_user(
            role=system_roles["department-head"], facility=facility_a, department=department_a
        )
    )
    body = head.get(f"{API}/leave-balances/?department={department_a.pk}").json()
    assert body["year"] == this_year()
    row = next(p for p in body["people"] if p["staff_id"] == str(staff.pk))
    assert {b["leave_type"] for b in row["balances"]} == {"annual", "sick"}
    other = make_user(role=system_roles["basic-staff"], facility=facility_a)
    assert (
        client_for(other).get(f"{API}/leave-balances/?department={department_a.pk}").status_code
        == 403
    )
    assert head.post(f"{API}/leave-entitlements/", {}, format="json").status_code == 403
    assert head.post(f"{API}/leave-adjustments/", {}, format="json").status_code == 403


@pytest.mark.django_db
def test_my_schedule_shows_my_own_balance(client_for, organization, department_a, person):
    _entitlement(days=10)
    staff = person(department_a)
    _joined(staff, date(this_year() - 1, 1, 1))
    mine = client_for(staff.user).get(f"{API}/my-schedule/").json()
    assert [(b["leave_type"], b["remaining"]) for b in mine["leave_balances"]] == [("annual", 10)]


@pytest.mark.django_db
def test_someone_with_no_staff_record_has_no_balances(client_for, make_user, organization):
    mine = client_for(make_user()).get(f"{API}/my-schedule/").json()
    assert mine["leave_balances"] == []


@pytest.mark.django_db
def test_hospital_settings_set_the_leave_year(client):
    body = client.get(f"{API}/organization/").json()
    assert body["leave_year_start_month"] == 1
    changed = client.patch(
        f"{API}/organization/", {"version": body["version"], "leave_year_start_month": 4}
    )
    assert changed.json()["leave_year_start_month"] == 4
    wrong = client.patch(
        f"{API}/organization/",
        {"version": changed.json()["version"], "leave_year_start_month": 13},
    )
    assert wrong.status_code == 400


@pytest.mark.django_db
def test_a_department_of_many_costs_few_queries(
    organization,
    department_a,
    person,
    django_assert_max_num_queries,
):
    _entitlement(days=10)
    made = [person(department_a).pk for _ in range(12)]
    people = list(StaffMember.objects.filter(pk__in=made))
    with django_assert_max_num_queries(5):
        found = balances.balances_for(people)
    assert all(len(rows) == 1 for rows in found.values())


@pytest.mark.django_db
def test_console_entitlements_and_adjustments_follow_the_same_rules(
    admin_user,
    organization,
    department_a,
    person,
):
    client = console(admin_user, confirmed=True)
    add = "/admin/rosters/leaveentitlement/add/"
    year = this_year()
    past = {
        "leave_type": "annual",
        "from_year": year - 1,
        "days": 10,
        "max_carry_over": 0,
        "tracked": "on",
    }
    refused = client.post(add, past)
    assert refused.status_code == 200 and "this leave year or later" in refused.content.decode()
    assert client.post(add, {**past, "from_year": year}).status_code == 302
    row = LeaveEntitlement.objects.get()
    assert row.updated_by == admin_user
    assert client.get(f"/admin/rosters/leaveentitlement/{row.pk}/change/").status_code == 200
    old = _entitlement(leave_type="sick", from_year=year - 1, days=5)
    assert (
        client.post(f"/admin/rosters/leaveentitlement/{old.pk}/change/", {"days": 6}).status_code
        == 403
    )
    staff = person(department_a)
    _joined(staff, date(year - 1, 1, 1))
    response = client.post(
        "/admin/rosters/leavebalanceadjustment/add/",
        {
            "staff": str(staff.pk),
            "leave_type": "annual",
            "leave_year": year,
            "days": 2,
            "reason": "Brought from old system",
        },
    )
    assert response.status_code == 302
    adjustment = LeaveBalanceAdjustment.objects.get()
    assert adjustment.created_by == admin_user
    # The rules show on the form, not as a server error.
    refused = client.post(
        "/admin/rosters/leavebalanceadjustment/add/",
        {
            "staff": str(staff.pk),
            "leave_type": "maternity",
            "leave_year": year,
            "days": 2,
            "reason": "x",
        },
    )
    assert refused.status_code == 200 and "no entitlement that year" in refused.content.decode()
    page = f"/admin/rosters/leavebalanceadjustment/{adjustment.pk}/change/"
    assert client.post(page, {"days": 9}).status_code == 403
    staff_page = client.get(f"/admin/staff/staffmember/{staff.pk}/change/").content.decode()
    assert "Leave balance this year" in staff_page and "Annual / earned leave" in staff_page


@pytest.mark.django_db
def test_console_approves_over_the_balance_only_with_its_own_action(
    admin_user,
    organization,
    department_a,
    person,
):
    _entitlement(days=0)
    staff = person(department_a)
    _joined(staff, date(this_year() - 1, 1, 1))
    start = hospital_today() + timedelta(days=5)
    leave = _leave(staff, department_a, start, start, status="requested")
    client = console(admin_user, confirmed=True)
    url = "/admin/rosters/leaverequest/"
    picked = {"_selected_action": [str(leave.pk)]}
    client.post(url, {"action": "approve_selected", **picked})
    leave.refresh_from_db()
    assert leave.status == "requested"
    client.post(url, {"action": "approve_over_balance", **picked})
    leave.refresh_from_db()
    assert leave.status == "approved"
