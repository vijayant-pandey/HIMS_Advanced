"""Bed board and bed status history (HIMS-FAC-008; spec 4.10, 15.1). All data is synthetic."""

import importlib

import pytest
from django.apps import apps as django_apps
from django.db import DatabaseError, connection, transaction
from django.test import Client

from apps.audit.services import AuditAction, record_audit_event
from apps.beds.models import Bed, BedStatusChange
from apps.beds.services import change_bed_status
from apps.beds.tests.test_locations_and_beds import build_structure
from apps.facilities.models import Ward
from apps.features.catalog import F
from apps.features.services import ensure_hospital_rows, set_feature

BOARD = "/api/v1/bed-board/"


def _status(client, bed_id, status, reason=""):
    version = Bed.objects.get(pk=bed_id).version
    body = {"version": version, "status": status, "reason": reason}
    return client.post(f"/api/v1/beds/{bed_id}/status/", body, format="json")


@pytest.fixture
def two_wards(client_for, admin_user, facility_a, department_a):
    """Ward w-gen (no department) and ward w-card (Cardiology), two beds each."""
    client = client_for(admin_user)
    general = build_structure(client, facility_a, ward_code="w-gen")
    floor = general["floor"]
    ward = client.post(
        "/api/v1/wards/",
        {"floor": floor, "code": "w-card", "name": "Cardiac Ward", "ward_type": "general"},
        format="json",
    ).json()
    Ward.objects.filter(pk=ward["id"]).update(department=department_a)
    room = client.post(
        "/api/v1/rooms/",
        {
            "ward": ward["id"],
            "code": "c1",
            "name": "Cardiac 1",
            "room_type": "isolation",
            "is_isolation_capable": True,
        },
        format="json",
    ).json()
    beds = client.post(
        "/api/v1/beds/bulk/",
        {"room": room["id"], "prefix": "c", "count": 2, "bed_type": "icu"},
        format="json",
    ).json()
    return {"general": general, "cardiac": {"ward": ward["id"], "beds": [b["id"] for b in beds]}}


@pytest.mark.django_db
def test_board_shows_every_ward_with_beds_counts_and_types(client_for, admin_user, two_wards):
    client = client_for(admin_user)
    _status(client, two_wards["general"]["beds"][0], "maintenance", "Broken side rail")
    body = client.get(BOARD).json()
    assert [f["code"] for f in body["facilities"]] == ["fac-a"]
    assert [w["code"] for w in body["wards"]] == ["w-card", "w-gen"]
    general = next(w for w in body["wards"] if w["code"] == "w-gen")
    assert general["bed_counts"] == {"maintenance": 1, "available": 1}
    assert general["can_change_status"] is True
    bed = general["beds"][0]
    assert (bed["code"], bed["status"], bed["status_reason"]) == (
        "b01",
        "maintenance",
        "Broken side rail",
    )
    assert bed["room_code"] == "r1" and bed["status_changed_at"]
    cardiac = next(w for w in body["wards"] if w["code"] == "w-card")
    assert cardiac["department_name"] == "Cardiology"
    assert cardiac["beds"][0]["is_isolation_capable"] is True
    assert body["bed_counts"] == {"maintenance": 1, "available": 3}
    assert body["available_by_type"] == {"general": 1, "icu": 2}


@pytest.mark.django_db
def test_switched_off_beds_and_rooms_are_not_on_the_board(client_for, admin_user, two_wards):
    client = client_for(admin_user)
    bed_id = two_wards["general"]["beds"][1]
    bed = Bed.objects.get(pk=bed_id)
    client.patch(
        f"/api/v1/beds/{bed_id}/", {"version": bed.version, "is_active": False}, format="json"
    )
    general = next(w for w in client.get(BOARD).json()["wards"] if w["code"] == "w-gen")
    assert [b["code"] for b in general["beds"]] == ["b01"]


@pytest.mark.django_db
def test_a_department_grant_sees_only_its_wards(
    client_for, make_user, system_roles, facility_a, department_a, two_wards
):
    nurse = make_user(
        role=system_roles["basic-staff"], facility=facility_a, department=department_a
    )
    body = client_for(nurse).get(BOARD).json()
    assert [w["code"] for w in body["wards"]] == ["w-card"]
    assert body["wards"][0]["can_change_status"] is False
    assert body["bed_counts"] == {"available": 2}


@pytest.mark.django_db
def test_a_department_bed_manager_changes_only_its_wards_beds(
    client_for, make_user, system_roles, facility_a, department_a, two_wards
):
    clerk = make_user(
        role=system_roles["bed-manager"], facility=facility_a, department=department_a
    )
    client = client_for(clerk)
    ward = client.get(BOARD).json()["wards"][0]
    assert (ward["code"], ward["can_change_status"]) == ("w-card", True)
    assert (
        _status(client, two_wards["cardiac"]["beds"][0], "blocked", "Monitor faulty").status_code
        == 200
    )
    refused = _status(client, two_wards["general"]["beds"][0], "blocked", "Not my ward")
    assert refused.status_code in (403, 404)
    assert Bed.objects.get(pk=two_wards["general"]["beds"][0]).status == Bed.Status.AVAILABLE


@pytest.mark.django_db
def test_people_without_locations_view_and_other_facilities(
    client_for, make_user, system_roles, admin_user, facility_a, facility_b, two_wards
):
    assert client_for(make_user()).get(BOARD).status_code == 403
    viewer = make_user(role=system_roles["basic-staff"], facility=facility_a)
    client = client_for(viewer)
    assert [f["id"] for f in client.get(BOARD).json()["facilities"]] == [str(facility_a.pk)]
    assert client.get(BOARD, {"facility": str(facility_b.pk)}).status_code == 404
    admin = client_for(admin_user)
    other = admin.get(BOARD, {"facility": str(facility_b.pk)}).json()
    assert (other["facility"], other["wards"]) == (str(facility_b.pk), [])


@pytest.mark.django_db
def test_facilities_with_locations_switched_off_are_left_out(
    client_for, admin_user, organization, facility_a, facility_b, two_wards
):
    ensure_hospital_rows(organization)
    set_feature(
        actor=admin_user,
        key=F.LOCATIONS,
        facility=facility_a,
        enabled=False,
        reason="Not used here yet",
        version=0,
    )
    body = client_for(admin_user).get(BOARD).json()
    assert str(facility_a.pk) not in [f["id"] for f in body["facilities"]]


@pytest.mark.django_db
def test_board_takes_a_fixed_number_of_queries(
    client_for, admin_user, two_wards, django_assert_max_num_queries
):
    client = client_for(admin_user)
    client.get(BOARD)  # warm the per-request caches the same way each time
    with django_assert_max_num_queries(25):
        client.get(BOARD)
    client.post(
        "/api/v1/beds/bulk/",
        {"room": two_wards["general"]["room"], "prefix": "x", "count": 20, "bed_type": "general"},
        format="json",
    )
    with django_assert_max_num_queries(25):
        assert len(client.get(BOARD).json()["wards"][1]["beds"]) == 22


# --- History ----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_every_status_change_is_kept_with_who_and_why(client_for, admin_user, two_wards):
    client = client_for(admin_user)
    bed_id = two_wards["general"]["beds"][0]
    _status(client, bed_id, "maintenance", "Broken side rail")
    _status(client, bed_id, "available", "Rail fixed")
    history = client.get(f"/api/v1/beds/{bed_id}/history/").json()
    assert [(h["from_status"], h["to_status"]) for h in history] == [
        ("maintenance", "available"),
        ("available", "maintenance"),
    ]
    assert history[0]["reason"] == "Rail fixed"
    assert history[1]["reason"] == "Broken side rail"
    assert history[0]["changed_by_name"] == admin_user.display_name


@pytest.mark.django_db
def test_switching_a_bed_off_is_kept_too(client_for, admin_user, two_wards):
    client = client_for(admin_user)
    bed_id = two_wards["general"]["beds"][1]
    bed = Bed.objects.get(pk=bed_id)
    client.patch(
        f"/api/v1/beds/{bed_id}/", {"version": bed.version, "is_active": False}, format="json"
    )
    change = BedStatusChange.objects.get(bed_id=bed_id)
    assert (change.from_status, change.to_status, change.reason) == (
        "available",
        "out_of_service",
        "Deactivated",
    )
    assert change.changed_by == admin_user
    # Creating beds and edits that keep the status add nothing.
    assert BedStatusChange.objects.count() == 1


@pytest.mark.django_db
def test_console_changes_are_kept_with_who(admin_user, two_wards):
    bed_id = two_wards["general"]["beds"][0]
    console = Client()
    console.force_login(admin_user)
    console.post(
        "/admin/beds/bed/", {"action": "mark_out_of_service", "_selected_action": [bed_id]}
    )
    change = BedStatusChange.objects.get(bed_id=bed_id)
    assert (change.to_status, change.changed_by, change.reason) == (
        "out_of_service",
        admin_user,
        "Set from admin console",
    )


@pytest.mark.django_db
def test_history_cannot_be_changed_or_deleted(admin_user, two_wards):
    bed = Bed.objects.get(pk=two_wards["general"]["beds"][0])
    change_bed_status(
        actor=admin_user,
        bed_id=bed.pk,
        version=bed.version,
        status="blocked",
        reason="Leaking oxygen point",
    )
    for sql in (
        "UPDATE bed_status_changes SET reason = 'changed'",
        "DELETE FROM bed_status_changes",
    ):
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql)
    assert BedStatusChange.objects.get().reason == "Leaking oxygen point"


@pytest.mark.django_db
def test_history_is_visible_only_where_the_bed_is(
    client_for, make_user, system_roles, facility_a, department_a, two_wards
):
    nurse = make_user(
        role=system_roles["basic-staff"], facility=facility_a, department=department_a
    )
    client = client_for(nurse)
    assert client.get(f"/api/v1/beds/{two_wards['cardiac']['beds'][0]}/history/").status_code == 200
    other = client.get(f"/api/v1/beds/{two_wards['general']['beds'][0]}/history/")
    assert other.status_code in (403, 404)


@pytest.mark.django_db
def test_changes_made_before_the_history_existed_are_copied_from_the_audit_log(
    admin_user, two_wards
):
    bed = Bed.objects.get(pk=two_wards["general"]["beds"][0])
    record_audit_event(
        action=AuditAction.BED_STATUS_CHANGED,
        resource_type="bed",
        resource_id=bed.pk,
        facility_id=bed.facility_id,
        actor=admin_user,
        reason="Old reason",
        changes={"before": {"status": "available"}, "after": {"status": "blocked"}},
    )
    migration = importlib.import_module("apps.beds.migrations.0002_bed_status_history")
    migration.copy_past_changes(django_apps, None)
    copied = BedStatusChange.objects.get(bed=bed)
    assert (copied.from_status, copied.to_status, copied.reason, copied.changed_by) == (
        "available",
        "blocked",
        "Old reason",
        admin_user,
    )


# --- Admin console ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_console_bed_board_and_history(admin_user, two_wards):
    bed_id = two_wards["general"]["beds"][0]
    bed = Bed.objects.get(pk=bed_id)
    change_bed_status(
        actor=admin_user,
        bed_id=bed.pk,
        version=bed.version,
        status="blocked",
        reason="Leaking oxygen point",
    )
    console = Client()
    console.force_login(admin_user)
    assert b"/admin/beds/bed/board/" in console.get("/admin/beds/bed/").content
    page = console.get("/admin/beds/bed/board/").content.decode()
    assert "Cardiac Ward (w-card)" in page and "General Ward (w-gen)" in page
    assert "Leaking oxygen point" in page
    detail = console.get(f"/admin/beds/bed/{bed_id}/change/").content.decode()
    assert "Status history" in detail and "Leaking oxygen point" in detail
    assert console.get("/admin/beds/bedstatuschange/").status_code == 200


@pytest.mark.django_db
def test_console_access_reviews_list_shows_when_the_next_one_is_due(admin_user):
    console = Client()
    console.force_login(admin_user)
    page = console.get("/admin/access_control/accessreview/").content.decode()
    assert "A full review is due every 90 days." in page
    assert "Next due:" in page
