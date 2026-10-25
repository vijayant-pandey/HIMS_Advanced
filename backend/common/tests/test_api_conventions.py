"""API-wide conventions: problem details, correlation IDs, authentication (spec 29.1)."""

import uuid

import pytest


@pytest.mark.django_db
def test_unauthenticated_request_gets_401_problem(client_for, organization):
    response = client_for().get("/api/v1/facilities/")
    assert response.status_code == 401
    assert response["Content-Type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "NOT_AUTHENTICATED"
    assert body["request_id"] == response["X-Request-ID"]


@pytest.mark.django_db
def test_inbound_request_id_is_echoed(client_for, admin_user):
    request_id = str(uuid.uuid4())
    response = client_for(admin_user).get("/api/v1/facilities/", HTTP_X_REQUEST_ID=request_id)
    assert response.status_code == 200
    assert response["X-Request-ID"] == request_id


@pytest.mark.django_db
def test_malformed_request_id_is_replaced(client_for, admin_user):
    response = client_for(admin_user).get(
        "/api/v1/facilities/", HTTP_X_REQUEST_ID="<script>alert(1)</script>"
    )
    assert response["X-Request-ID"] != "<script>alert(1)</script>"
    uuid.UUID(response["X-Request-ID"])


@pytest.mark.django_db
def test_validation_errors_are_listed_per_field(client_for, admin_user):
    response = client_for(admin_user).post("/api/v1/facilities/", {"code": "x"}, format="json")
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    fields = {error["field"] for error in body["errors"]}
    assert {"name", "timezone", "facility_type"} <= fields


@pytest.mark.django_db
def test_unknown_resource_is_404_problem(client_for, admin_user):
    response = client_for(admin_user).get(f"/api/v1/facilities/{uuid.uuid4()}/")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.django_db
def test_health_endpoints_need_no_auth(client_for):
    client = client_for()
    assert client.get("/health/live/").status_code == 200
    assert client.get("/health/ready/").status_code == 200
