import pytest

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction

FACILITY = {
    "code": "south",
    "name": "South Branch",
    "facility_type": "hospital",
    "country": "IN",
    "state_region": "Tamil Nadu",
    "city": "Chennai",
    "address_line1": "3 Synthetic Road",
    "postal_code": "600001",
    "timezone": "Asia/Kolkata",
}


@pytest.mark.django_db
def test_create_facility_is_audited(client_for, admin_user):
    response = client_for(admin_user).post("/api/v1/facilities/", FACILITY, format="json")
    assert response.status_code == 201
    facility_id = response.json()["id"]
    event = AuditEvent.objects.get(action=AuditAction.FACILITY_CREATED, resource_id=facility_id)
    assert event.actor_id == admin_user.pk
    assert event.changes["after"]["code"] == "south"


@pytest.mark.django_db
def test_duplicate_code_is_conflict(client_for, admin_user):
    client = client_for(admin_user)
    client.post("/api/v1/facilities/", FACILITY, format="json")
    response = client.post("/api/v1/facilities/", FACILITY, format="json")
    assert response.status_code == 409
    assert response.json()["code"] == "DUPLICATE_CODE"


@pytest.mark.django_db
def test_invalid_timezone_rejected(client_for, admin_user):
    response = client_for(admin_user).post(
        "/api/v1/facilities/", {**FACILITY, "timezone": "Asia/Atlantis"}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_stale_update_is_rejected_and_change_is_audited(client_for, admin_user, facility_a):
    client = client_for(admin_user)
    url = f"/api/v1/facilities/{facility_a.pk}/"
    assert (
        client.patch(url, {"version": 1, "phone": "+91-80-0000"}, format="json").status_code == 200
    )
    stale = client.patch(url, {"version": 1, "phone": "+91-80-1111"}, format="json")
    assert stale.status_code == 409

    event = AuditEvent.objects.get(action=AuditAction.FACILITY_UPDATED)
    assert event.changes == {"before": {"phone": ""}, "after": {"phone": "+91-80-0000"}}


@pytest.mark.django_db
def test_department_cannot_be_added_to_inactive_facility(client_for, admin_user, facility_a):
    facility_a.status = "inactive"
    facility_a.save()
    response = client_for(admin_user).post(
        "/api/v1/departments/",
        {
            "facility": str(facility_a.pk),
            "code": "icu",
            "name": "ICU",
            "department_type": "clinical",
        },
        format="json",
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_department_list_filters_by_facility(client_for, admin_user, department_a, facility_b):
    client = client_for(admin_user)
    ids = [d["id"] for d in client.get("/api/v1/departments/").json()["results"]]
    assert ids == [str(department_a.pk)]
    filtered = client.get("/api/v1/departments/", {"facility": str(facility_b.pk)})
    assert filtered.json()["results"] == []
