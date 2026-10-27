"""Locations (building → floor → ward → room) and beds, HIMS-FAC-004. All data is synthetic."""

import pytest
from django.test import override_settings

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.beds.models import Bed
from common.outbox.models import OutboxEvent

API = "/api/v1"


def build_structure(client, facility, *, ward_code="w-gen", beds=2):
    """Create building → floor → ward → room → beds through the API; return the ids."""
    building = client.post(
        f"{API}/buildings/",
        {"facility": str(facility.pk), "code": "main", "name": "Main"},
        format="json",
    )
    assert building.status_code == 201, building.json()
    floor = client.post(
        f"{API}/floors/",
        {"building": building.json()["id"], "level": 2, "name": "Second"},
        format="json",
    )
    assert floor.status_code == 201, floor.json()
    ward = client.post(
        f"{API}/wards/",
        {
            "floor": floor.json()["id"],
            "code": ward_code,
            "name": "General Ward",
            "ward_type": "general",
        },
        format="json",
    )
    assert ward.status_code == 201, ward.json()
    room = client.post(
        f"{API}/rooms/",
        {"ward": ward.json()["id"], "code": "r1", "name": "Room 1", "room_type": "general"},
        format="json",
    )
    assert room.status_code == 201, room.json()
    bulk = client.post(
        f"{API}/beds/bulk/",
        {"room": room.json()["id"], "prefix": "b", "count": beds, "bed_type": "general"},
        format="json",
    )
    assert bulk.status_code == 201, bulk.json()
    return {
        "building": building.json()["id"],
        "floor": floor.json()["id"],
        "ward": ward.json()["id"],
        "room": room.json()["id"],
        "beds": [bed["id"] for bed in bulk.json()],
    }


@pytest.mark.django_db
def test_admin_builds_full_hierarchy_and_every_step_is_audited(client_for, admin_user, facility_a):
    client = client_for(admin_user)
    ids = build_structure(client, facility_a, beds=3)

    beds = Bed.objects.filter(pk__in=ids["beds"]).order_by("code")
    assert [bed.code for bed in beds] == ["b01", "b02", "b03"]
    bed = beds[0]
    # facility and ward are derived from the parent, never sent by the client
    assert bed.facility_id == facility_a.pk
    assert str(bed.ward_id) == ids["ward"]
    assert bed.organization_id == facility_a.organization_id
    assert bed.status == Bed.Status.AVAILABLE
    created = AuditEvent.objects.filter(action=AuditAction.LOCATION_CREATED)
    assert created.count() == 4 + 3  # building, floor, ward, room + 3 beds
    assert set(created.values_list("facility_id", flat=True)) == {facility_a.pk}


@pytest.mark.django_db
def test_duplicate_codes_and_floor_levels_are_refused(client_for, admin_user, facility_a):
    client = client_for(admin_user)
    ids = build_structure(client, facility_a)
    again = client.post(
        f"{API}/buildings/",
        {"facility": str(facility_a.pk), "code": "main", "name": "X"},
        format="json",
    )
    assert again.status_code == 400
    same_level = client.post(
        f"{API}/floors/", {"building": ids["building"], "level": 2, "name": "Dup"}, format="json"
    )
    assert same_level.status_code == 400
    bulk_clash = client.post(
        f"{API}/beds/bulk/",
        {"room": ids["room"], "prefix": "b", "count": 3, "bed_type": "general"},
        format="json",
    )
    assert bulk_clash.status_code == 409
    assert bulk_clash.json()["code"] == "DUPLICATE_CODE"
    assert Bed.objects.count() == 2  # nothing partially created


@pytest.mark.django_db
def test_parent_cannot_change_and_codes_are_not_editable(client_for, admin_user, facility_a):
    client = client_for(admin_user)
    ids = build_structure(client, facility_a)
    response = client.patch(
        f"{API}/rooms/{ids['room']}/",
        {"version": 1, "code": "zz", "ward": ids["ward"]},
        format="json",
    )
    assert response.status_code == 200  # unknown fields are ignored, not applied
    room = client.get(f"{API}/rooms/{ids['room']}/").json()
    assert room["code"] == "r1"
    assert room["ward"] == ids["ward"]


@pytest.mark.django_db
def test_deactivation_order_is_enforced(client_for, admin_user, facility_a):
    client = client_for(admin_user)
    ids = build_structure(client, facility_a, beds=1)
    room_off = client.patch(
        f"{API}/rooms/{ids['room']}/", {"version": 1, "is_active": False}, format="json"
    )
    assert room_off.status_code == 400  # it still has an active bed

    bed_off = client.patch(
        f"{API}/beds/{ids['beds'][0]}/", {"version": 1, "is_active": False}, format="json"
    )
    assert bed_off.status_code == 200
    assert bed_off.json()["status"] == "out_of_service"
    assert bed_off.json()["status_reason"] == "Deactivated"

    room_off = client.patch(
        f"{API}/rooms/{ids['room']}/", {"version": 1, "is_active": False}, format="json"
    )
    assert room_off.status_code == 200
    # nothing new can be added under an inactive room
    new_bed = client.post(
        f"{API}/beds/", {"room": ids["room"], "code": "b09", "bed_type": "general"}, format="json"
    )
    assert new_bed.status_code == 400


@pytest.mark.django_db
def test_ward_department_must_be_in_same_facility(client_for, admin_user, facility_a, facility_b):
    from apps.facilities.models import Department

    other = Department.objects.create(
        organization_id=facility_b.organization_id,
        facility=facility_b,
        code="ortho",
        name="Orthopaedics",
        department_type=Department.DepartmentType.CLINICAL,
    )
    client = client_for(admin_user)
    ids = build_structure(client, facility_a)
    response = client.post(
        f"{API}/wards/",
        {
            "floor": ids["floor"],
            "code": "w2",
            "name": "W2",
            "ward_type": "general",
            "department": str(other.pk),
        },
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_stale_version_is_conflict(client_for, admin_user, facility_a):
    client = client_for(admin_user)
    ids = build_structure(client, facility_a)
    url = f"{API}/wards/{ids['ward']}/"
    assert client.patch(url, {"version": 1, "name": "Ward A"}, format="json").status_code == 200
    assert client.patch(url, {"version": 1, "name": "Ward B"}, format="json").status_code == 409
    event = AuditEvent.objects.get(action=AuditAction.LOCATION_UPDATED, resource_id=ids["ward"])
    assert event.changes == {"before": {"name": "General Ward"}, "after": {"name": "Ward A"}}


# --- Bed status state machine --------------------------------------------------------------


@pytest.mark.django_db
def test_bed_status_change_needs_reason_and_is_audited_and_published(
    client_for, admin_user, facility_a
):
    client = client_for(admin_user)
    bed_id = build_structure(client, facility_a, beds=1)["beds"][0]
    url = f"{API}/beds/{bed_id}/status/"

    no_reason = client.post(url, {"version": 1, "status": "maintenance"}, format="json")
    assert no_reason.status_code == 400
    assert no_reason.json()["code"] == "STATUS_REASON_REQUIRED"

    ok = client.post(
        url, {"version": 1, "status": "maintenance", "reason": "Broken side rail"}, format="json"
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "maintenance"
    assert ok.json()["version"] == 2

    event = AuditEvent.objects.get(action=AuditAction.BED_STATUS_CHANGED)
    assert event.changes == {"before": {"status": "available"}, "after": {"status": "maintenance"}}
    assert event.reason == "Broken side rail"
    outbox = OutboxEvent.objects.get(event_type="bed.status.changed")
    assert outbox.payload["to"] == "maintenance"
    assert "reason" not in outbox.payload

    back = client.post(url, {"version": 2, "status": "available"}, format="json")
    assert back.status_code == 200
    assert back.json()["status_reason"] == ""


@pytest.mark.django_db
@pytest.mark.parametrize("target", ["reserved", "occupied", "cleaning"])
def test_admission_states_cannot_be_set_by_hand(client_for, admin_user, facility_a, target):
    client = client_for(admin_user)
    bed_id = build_structure(client, facility_a, beds=1)["beds"][0]
    response = client.post(
        f"{API}/beds/{bed_id}/status/",
        {"version": 1, "status": target, "reason": "x"},
        format="json",
    )
    assert response.status_code == 400  # not an allowed choice


@pytest.mark.django_db
def test_occupied_bed_cannot_be_changed_or_deactivated(client_for, admin_user, facility_a):
    client = client_for(admin_user)
    bed_id = build_structure(client, facility_a, beds=1)["beds"][0]
    Bed.objects.filter(pk=bed_id).update(status=Bed.Status.OCCUPIED)  # as Phase 3 ADT will

    response = client.post(
        f"{API}/beds/{bed_id}/status/", {"version": 1, "status": "available"}, format="json"
    )
    assert response.status_code == 409
    assert response.json()["code"] == "BED_STATUS_MANAGED_BY_ADT"
    deactivate = client.patch(
        f"{API}/beds/{bed_id}/", {"version": 1, "is_active": False}, format="json"
    )
    assert deactivate.status_code == 400


@pytest.mark.django_db
def test_stale_status_change_is_conflict(client_for, admin_user, facility_a):
    client = client_for(admin_user)
    bed_id = build_structure(client, facility_a, beds=1)["beds"][0]
    url = f"{API}/beds/{bed_id}/status/"
    client.post(
        url, {"version": 1, "status": "blocked", "reason": "Infection control"}, format="json"
    )
    stale = client.post(url, {"version": 1, "status": "available"}, format="json")
    assert stale.status_code == 409


# --- Tree, permissions and scope -----------------------------------------------------------


@pytest.mark.django_db
def test_facility_tree_has_counts(client_for, admin_user, facility_a):
    client = client_for(admin_user)
    ids = build_structure(client, facility_a, beds=3)
    client.post(
        f"{API}/beds/{ids['beds'][0]}/status/",
        {"version": 1, "status": "maintenance", "reason": "Mattress change"},
        format="json",
    )
    tree = client.get(f"{API}/facilities/{facility_a.pk}/locations/").json()
    assert tree["bed_counts"] == {"available": 2, "maintenance": 1}
    ward = tree["buildings"][0]["floors"][0]["wards"][0]
    assert ward["bed_counts"] == {"available": 2, "maintenance": 1}
    assert [bed["code"] for bed in ward["rooms"][0]["beds"]] == ["b01", "b02", "b03"]


@pytest.mark.django_db
def test_bed_manager_changes_status_only_in_own_facility(
    client_for, admin_user, make_user, system_roles, facility_a, facility_b
):
    admin = client_for(admin_user)
    bed_a = build_structure(admin, facility_a, beds=1)["beds"][0]
    bed_b = build_structure(admin, facility_b, ward_code="w-b", beds=1)["beds"][0]
    clerk = client_for(make_user(role=system_roles["bed-manager"], facility=facility_a))

    ok = clerk.post(
        f"{API}/beds/{bed_a}/status/",
        {"version": 1, "status": "blocked", "reason": "Leak"},
        format="json",
    )
    assert ok.status_code == 200
    other = clerk.post(
        f"{API}/beds/{bed_b}/status/",
        {"version": 1, "status": "blocked", "reason": "Leak"},
        format="json",
    )
    assert other.status_code == 404  # out of scope looks the same as missing
    assert len(clerk.get(f"{API}/beds/").json()["results"]) == 1
    assert clerk.get(f"{API}/facilities/{facility_b.pk}/locations/").status_code == 404
    # a bed manager cannot change the structure
    assert (
        clerk.patch(
            f"{API}/beds/{bed_a}/", {"version": 2, "bed_type": "icu"}, format="json"
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_basic_staff_can_view_but_not_change(
    client_for, admin_user, make_user, system_roles, facility_a
):
    ids = build_structure(client_for(admin_user), facility_a, beds=1)
    staff = client_for(make_user(role=system_roles["basic-staff"], facility=facility_a))
    assert staff.get(f"{API}/facilities/{facility_a.pk}/locations/").status_code == 200
    assert staff.get(f"{API}/wards/?facility={facility_a.pk}").status_code == 200
    denied = staff.post(
        f"{API}/beds/{ids['beds'][0]}/status/",
        {"version": 1, "status": "blocked", "reason": "x"},
        format="json",
    )
    assert denied.status_code == 403
    assert (
        staff.post(
            f"{API}/buildings/",
            {"facility": str(facility_a.pk), "code": "x", "name": "X"},
            format="json",
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_facility_admin_cannot_create_in_another_facility(
    client_for, make_user, system_roles, facility_a, facility_b
):
    fac_admin = client_for(
        make_user(role=system_roles["facility-administrator"], facility=facility_a)
    )
    own = fac_admin.post(
        f"{API}/buildings/",
        {"facility": str(facility_a.pk), "code": "a", "name": "A"},
        format="json",
    )
    assert own.status_code == 201
    other = fac_admin.post(
        f"{API}/buildings/",
        {"facility": str(facility_b.pk), "code": "b", "name": "B"},
        format="json",
    )
    assert other.status_code == 403


@pytest.mark.django_db
def test_managing_locations_requires_two_factor(make_user, system_roles, facility_a):
    from apps.identity.mfa import is_required

    fac_admin = make_user(role=system_roles["facility-administrator"], facility=facility_a)
    clerk = make_user(role=system_roles["bed-manager"], facility=facility_a)
    with override_settings(HIMS_MFA_REQUIRED_FOR_PRIVILEGED=True):
        assert is_required(fac_admin)
        assert not is_required(clerk)  # bed status changes are routine ward work
