import threading

import pytest
from django.db import connection

from apps.facilities.models import Facility

FACILITY = {
    "code": "north",
    "name": "North Branch",
    "facility_type": "hospital",
    "country": "IN",
    "state_region": "Karnataka",
    "city": "Bengaluru",
    "address_line1": "2 Synthetic Road",
    "postal_code": "560002",
    "timezone": "Asia/Kolkata",
}


@pytest.mark.django_db
def test_same_key_and_body_replays_original_response(client_for, admin_user):
    client = client_for(admin_user)
    headers = {"HTTP_IDEMPOTENCY_KEY": "key-0000000001"}
    first = client.post("/api/v1/facilities/", FACILITY, format="json", **headers)
    second = client.post("/api/v1/facilities/", FACILITY, format="json", **headers)

    assert first.status_code == second.status_code == 201
    assert second["Idempotent-Replayed"] == "true"
    assert second.json()["id"] == first.json()["id"]
    assert Facility.objects.filter(code="north").count() == 1


@pytest.mark.django_db
def test_same_key_with_different_body_conflicts(client_for, admin_user):
    client = client_for(admin_user)
    headers = {"HTTP_IDEMPOTENCY_KEY": "key-0000000002"}
    client.post("/api/v1/facilities/", FACILITY, format="json", **headers)
    response = client.post(
        "/api/v1/facilities/", {**FACILITY, "name": "Other"}, format="json", **headers
    )
    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.django_db
def test_failed_request_is_not_cached(client_for, admin_user):
    client = client_for(admin_user)
    headers = {"HTTP_IDEMPOTENCY_KEY": "key-0000000003"}
    bad = client.post(
        "/api/v1/facilities/", {**FACILITY, "timezone": "Mars/Base"}, format="json", **headers
    )
    assert bad.status_code == 400
    good = client.post("/api/v1/facilities/", FACILITY, format="json", **headers)
    # The key now maps to a different (valid) body; nothing was stored for the failed attempt.
    assert good.status_code == 201


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicates_create_exactly_one_record(client_for, admin_user):
    barrier = threading.Barrier(4)
    results = []

    def submit():
        try:
            client = client_for(admin_user)
            barrier.wait()
            response = client.post(
                "/api/v1/facilities/",
                FACILITY,
                format="json",
                HTTP_IDEMPOTENCY_KEY="key-concurrent-01",
            )
            results.append(response.status_code)
        finally:
            connection.close()

    threads = [threading.Thread(target=submit) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == [201, 201, 201, 201]
    assert Facility.objects.filter(code="north").count() == 1
