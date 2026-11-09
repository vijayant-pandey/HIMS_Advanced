"""Equipment register (HIMS-FAC-009; spec 4.12). All data is synthetic."""

from datetime import timedelta

import pytest
from django.db import DatabaseError, transaction

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.equipment.models import Equipment, EquipmentServiceRecord
from apps.equipment.services import DUE_SOON, OVERDUE, due_state, filter_due
from apps.facilities.models import Department
from apps.features.catalog import F
from apps.features.services import ensure_hospital_rows, set_feature
from apps.organizations.dates import hospital_today
from common.admin.tests.test_console_additions import console

LIST = "/api/v1/equipment/"


def _add(client, facility, tag="vent-01", **extra):
    body = {"facility": str(facility.pk), "asset_tag": tag, "name": "Ventilator", **extra}
    return client.post(LIST, body, format="json")


def _visit(client, item_id, **extra):
    today = hospital_today()
    body = {"kind": "service", "performed_on": today.isoformat(), **extra}
    return client.post(f"{LIST}{item_id}/service-records/", body, format="json")


@pytest.fixture
def client(client_for, admin_user):
    return client_for(admin_user)


@pytest.mark.django_db
def test_add_and_see_equipment_with_where_it_is(client, facility_a, department_a):
    response = _add(
        client,
        facility_a,
        department=str(department_a.pk),
        category="life_support",
        serial_number="SN-1",
        location_note="Store 2",
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["asset_tag"] == "VENT-01"  # labels are written in capitals
    assert body["status"] == "in_service"
    assert body["department_name"] == department_a.name
    assert body["location_note"] == "Store 2"
    assert body["category_label"].startswith("Life support")
    assert AuditEvent.objects.filter(action=AuditAction.EQUIPMENT_CREATED).count() == 1
    assert client.get(LIST).json()["count"] == 1


@pytest.mark.django_db
def test_a_tag_is_unique_per_facility_and_set_once(client, facility_a, facility_b):
    item = _add(client, facility_a).json()
    assert _add(client, facility_a).status_code == 400
    assert _add(client, facility_b).status_code == 201  # another branch may use the same number
    changed = client.patch(
        f"{LIST}{item['id']}/",
        {"version": item["version"], "asset_tag": "OTHER", "name": "New name"},
        format="json",
    ).json()
    assert changed["asset_tag"] == "VENT-01" and changed["name"] == "New name"


@pytest.mark.django_db
def test_a_location_must_belong_to_the_same_facility(client, facility_a, facility_b):
    other = Department.objects.create(
        organization=facility_b.organization, facility=facility_b, name="Other", code="OTH"
    )
    response = _add(client, facility_a, department=str(other.pk))
    assert response.status_code == 400
    assert "another facility" in str(response.json())


@pytest.mark.django_db
def test_changing_needs_the_current_version(client, facility_a):
    item = _add(client, facility_a).json()
    url = f"{LIST}{item['id']}/"
    assert client.patch(url, {"version": 1, "name": "A"}, format="json").status_code == 200
    assert client.patch(url, {"version": 1, "name": "B"}, format="json").status_code == 409


@pytest.mark.django_db
def test_status_needs_a_reason_unless_in_service_and_is_audited(client, facility_a):
    item = _add(client, facility_a).json()
    url = f"{LIST}{item['id']}/status/"
    refused = client.post(url, {"version": 1, "status": "maintenance"}, format="json")
    assert refused.status_code == 400
    changed = client.post(
        url, {"version": 1, "status": "maintenance", "reason": "Battery fault"}, format="json"
    ).json()
    assert (changed["status_label"], changed["status_reason"]) == (
        "Under maintenance",
        "Battery fault",
    )
    event = AuditEvent.objects.get(action=AuditAction.EQUIPMENT_STATUS_CHANGED)
    assert event.changes["after"] == {"status": "maintenance"}
    back = client.post(
        url, {"version": changed["version"], "status": "in_service"}, format="json"
    ).json()
    assert back["status_reason"] == ""


@pytest.mark.django_db
def test_a_visit_sets_the_dates_and_joins_the_history(client, facility_a):
    item = _add(client, facility_a).json()
    today = hospital_today()
    due = today + timedelta(days=180)
    response = _visit(client, item["id"], performed_by="Acme Biomed", next_due=due.isoformat())
    assert response.status_code == 201, response.content
    assert response.json()["recorded_by_name"]
    fresh = client.get(f"{LIST}{item['id']}/").json()
    assert fresh["last_service_on"] == today.isoformat()
    assert fresh["next_service_due"] == due.isoformat()
    assert fresh["version"] == item["version"] + 1
    _visit(client, item["id"], kind="calibration", next_due=due.isoformat())
    fresh = client.get(f"{LIST}{item['id']}/").json()
    assert fresh["last_calibrated_on"] == today.isoformat()
    history = client.get(f"{LIST}{item['id']}/history/").json()
    assert {row["kind"] for row in history} == {"service", "calibration"}
    assert AuditEvent.objects.filter(action=AuditAction.EQUIPMENT_SERVICE_RECORDED).count() == 2


@pytest.mark.django_db
def test_an_older_visit_entered_late_does_not_move_the_dates(client, facility_a):
    item = _add(client, facility_a).json()
    today = hospital_today()
    due = today + timedelta(days=90)
    _visit(client, item["id"], next_due=due.isoformat())
    late = today - timedelta(days=60)
    assert _visit(client, item["id"], performed_on=late.isoformat()).status_code == 201
    fresh = client.get(f"{LIST}{item['id']}/").json()
    assert fresh["last_service_on"] == today.isoformat()
    assert fresh["next_service_due"] == due.isoformat()
    assert len(client.get(f"{LIST}{item['id']}/history/").json()) == 2


@pytest.mark.django_db
def test_visit_dates_are_checked_and_a_retired_item_takes_no_visits(client, facility_a):
    item = _add(client, facility_a).json()
    today = hospital_today()
    future = (today + timedelta(days=1)).isoformat()
    assert _visit(client, item["id"], performed_on=future).status_code == 400
    assert _visit(client, item["id"], next_due=today.isoformat()).status_code == 400
    client.post(
        f"{LIST}{item['id']}/status/",
        {"version": 1, "status": "retired", "reason": "Too old"},
        format="json",
    )
    response = _visit(client, item["id"])
    assert response.status_code == 409
    assert response.json()["code"] == "EQUIPMENT_RETIRED"


@pytest.mark.django_db
def test_visits_cannot_be_changed_or_deleted_even_directly(client, facility_a):
    item = _add(client, facility_a).json()
    _visit(client, item["id"])
    record = EquipmentServiceRecord.objects.get()
    with pytest.raises(DatabaseError), transaction.atomic():
        EquipmentServiceRecord.objects.filter(pk=record.pk).update(notes="changed")
    with pytest.raises(DatabaseError), transaction.atomic():
        EquipmentServiceRecord.objects.filter(pk=record.pk).delete()


@pytest.mark.django_db
def test_due_state_and_its_list_filter_agree(client, facility_a):
    today = hospital_today()
    past = (today - timedelta(days=1)).isoformat()
    soon = (today + timedelta(days=10)).isoformat()
    later = (today + timedelta(days=200)).isoformat()
    overdue = _add(client, facility_a, "a", next_service_due=past).json()
    # Calibration overdue while the service is far off: the earlier date decides.
    mixed = _add(client, facility_a, "b", next_service_due=later, next_calibration_due=past).json()
    upcoming = _add(client, facility_a, "c", next_calibration_due=soon).json()
    _add(client, facility_a, "d", next_service_due=later)
    _add(client, facility_a, "e")
    retired = _add(client, facility_a, "f", next_service_due=past).json()
    client.post(
        f"{LIST}{retired['id']}/status/",
        {"version": 1, "status": "retired", "reason": "Scrapped"},
        format="json",
    )
    assert client.get(f"{LIST}{overdue['id']}/").json()["due_state"] == OVERDUE
    assert client.get(f"{LIST}{mixed['id']}/").json()["due_state"] == OVERDUE
    assert client.get(f"{LIST}{upcoming['id']}/").json()["due_state"] == DUE_SOON
    tags = lambda due: {r["asset_tag"] for r in client.get(f"{LIST}?due={due}").json()["results"]}  # noqa: E731
    assert tags(OVERDUE) == {"A", "B"}
    assert tags(DUE_SOON) == {"C"}
    for item in Equipment.objects.all():
        for state in (OVERDUE, DUE_SOON):
            listed = filter_due(Equipment.objects.filter(pk=item.pk), state).exists()
            assert listed == (due_state(item) == state), item.asset_tag


@pytest.mark.django_db
def test_lists_filter_by_status_category_and_search(client, facility_a):
    _add(client, facility_a, "m1", name="Bedside monitor", category="monitoring")
    pump = _add(client, facility_a, "p1", name="Syringe pump", category="infusion").json()
    client.post(
        f"{LIST}{pump['id']}/status/",
        {"version": 1, "status": "out_of_service", "reason": "Broken"},
        format="json",
    )
    names = lambda query: [r["name"] for r in client.get(f"{LIST}?{query}").json()["results"]]  # noqa: E731
    assert names("category=monitoring") == ["Bedside monitor"]
    assert names("status=out_of_service") == ["Syringe pump"]
    assert names("search=syringe") == ["Syringe pump"]


@pytest.mark.django_db
def test_a_department_grant_sees_and_manages_only_its_department(
    client_for, make_user, system_roles, admin_user, facility_a, facility_b, department_a
):
    admin = client_for(admin_user)
    mine = _add(admin, facility_a, "mine", department=str(department_a.pk)).json()
    other = _add(admin, facility_a, "general").json()
    elsewhere = _add(admin, facility_b, "far").json()
    officer = client_for(
        make_user(
            role=system_roles["equipment-officer"], facility=facility_a, department=department_a
        )
    )
    assert [r["id"] for r in officer.get(LIST).json()["results"]] == [mine["id"]]
    assert officer.get(f"{LIST}{other['id']}/").status_code == 404
    assert officer.get(f"{LIST}{elsewhere['id']}/").status_code == 404
    assert _visit(officer, mine["id"]).status_code == 201
    assert _visit(officer, other["id"]).status_code == 404
    # May add to their department, not to the facility in general.
    assert _add(officer, facility_a, "new", department=str(department_a.pk)).status_code == 201
    assert _add(officer, facility_a, "open").status_code == 403


@pytest.mark.django_db
def test_who_may_see_and_change(client_for, make_user, system_roles, facility_a, admin_user):
    item = _add(client_for(admin_user), facility_a).json()
    assert client_for(make_user()).get(LIST).status_code == 403
    assert (
        client_for(make_user(role=system_roles["basic-staff"], facility=facility_a))
        .get(LIST)
        .status_code
        == 403
    )
    head = client_for(make_user(role=system_roles["department-head"], facility=facility_a))
    assert head.get(LIST).json()["count"] == 1  # looks, does not change
    assert (
        head.patch(
            f"{LIST}{item['id']}/", {"version": 1, "name": "Changed"}, format="json"
        ).status_code
        == 403
    )
    assert _add(head, facility_a, "x").status_code == 403


@pytest.mark.django_db
def test_switching_the_register_off_closes_it_for_that_facility(
    client, admin_user, facility_a, facility_b, organization
):
    ensure_hospital_rows(organization)
    item = _add(client, facility_a).json()
    _add(client, facility_b, "far")
    set_feature(
        actor=admin_user,
        key=F.EQUIPMENT,
        facility=facility_a,
        enabled=False,
        reason="Not used here yet",
        version=0,
    )
    assert [r["asset_tag"] for r in client.get(LIST).json()["results"]] == ["FAR"]
    closed = client.get(f"{LIST}{item['id']}/")
    assert closed.status_code == 409 and closed.json()["code"] == "FEATURE_DISABLED"
    assert _add(client, facility_a, "new").status_code == 409


@pytest.mark.django_db
def test_console_status_goes_through_the_same_rules(admin_user, client_for, facility_a):
    item = _add(client_for(admin_user), facility_a).json()
    client = console(admin_user, confirmed=True)
    url = f"/admin/equipment/equipment/{item['id']}/change/"
    assert client.get(url).status_code == 200
    data = {
        "name": "Ventilator",
        "category": "other",
        "new_status": "maintenance",
        "new_status_reason": "",
    }
    refused = client.post(url, data)
    assert refused.status_code == 200
    assert "Say why" in refused.content.decode()
    assert client.post(url, {**data, "new_status_reason": "Battery fault"}).status_code == 302
    fresh = Equipment.objects.get(pk=item["id"])
    assert (fresh.status, fresh.status_reason) == ("maintenance", "Battery fault")
    assert AuditEvent.objects.filter(action=AuditAction.EQUIPMENT_STATUS_CHANGED).count() == 1


@pytest.mark.django_db
def test_console_adds_equipment_and_refuses_a_tag_already_used(
    admin_user, facility_a, organization
):
    client = console(admin_user, confirmed=True)
    add = "/admin/equipment/equipment/add/"
    assert client.get(add).status_code == 200
    data = {
        "organization": str(organization.pk),
        "facility": str(facility_a.pk),
        "asset_tag": "vent-7",
        "name": "Ventilator",
        "category": "other",
    }
    assert client.post(add, data).status_code == 302
    item = Equipment.objects.get()
    assert item.asset_tag == "VENT-7" and item.status == "in_service"
    assert item.organization == organization
    again = client.post(add, data)  # the same tag again, written the same way
    assert again.status_code == 200
    assert Equipment.objects.count() == 1


@pytest.mark.django_db
def test_console_adds_a_visit_and_cannot_change_one(admin_user, client_for, facility_a):
    item = _add(client_for(admin_user), facility_a).json()
    client = console(admin_user, confirmed=True)
    add = "/admin/equipment/equipmentservicerecord/add/"
    assert client.get(add).status_code == 200
    today = hospital_today()
    response = client.post(
        add,
        {
            "equipment": item["id"],
            "kind": "calibration",
            "performed_on": today.isoformat(),
            "next_due": (today + timedelta(days=30)).isoformat(),
        },
    )
    assert response.status_code == 302
    record = EquipmentServiceRecord.objects.get()
    assert record.recorded_by == admin_user and str(record.facility_id) == str(facility_a.pk)
    assert Equipment.objects.get(pk=item["id"]).last_calibrated_on == today
    page = f"/admin/equipment/equipmentservicerecord/{record.pk}/change/"
    assert client.get(page).status_code == 200
    assert client.post(page, {"notes": "changed"}).status_code == 403
    item_page = client.get(f"/admin/equipment/equipment/{item['id']}/change/")
    assert "Calibration" in item_page.content.decode()
