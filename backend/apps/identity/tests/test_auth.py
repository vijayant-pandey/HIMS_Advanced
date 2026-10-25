import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction

PASSWORD = "Synthetic-Passw0rd-For-Tests"


@pytest.fixture(autouse=True)
def _reset_throttle():
    cache.clear()


@pytest.fixture
def csrf_client():
    client = APIClient(enforce_csrf_checks=True)
    client.get("/api/v1/auth/csrf/")
    return client, client.cookies["hims_csrftoken"].value


@pytest.fixture
def user(make_user, system_roles):
    return make_user(
        email="doctor@synthetic.test",
        password=PASSWORD,
        role=system_roles["organization-administrator"],
    )


def _login(client, token, email, password):
    return client.post(
        "/api/v1/auth/login/",
        {"email": email, "password": password},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )


@pytest.mark.django_db
def test_login_establishes_session_and_returns_grants(csrf_client, user):
    client, token = csrf_client
    response = _login(client, token, "Doctor@Synthetic.TEST", PASSWORD)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "doctor@synthetic.test"
    assert any(g["permission"] == "facilities.manage" for g in body["grants"])
    assert client.get("/api/v1/auth/me/").status_code == 200
    assert AuditEvent.objects.filter(action=AuditAction.AUTH_LOGIN, actor_id=user.pk).exists()


@pytest.mark.django_db
def test_login_requires_csrf_token(user):
    client = APIClient(enforce_csrf_checks=True)
    response = client.post(
        "/api/v1/auth/login/", {"email": user.email, "password": PASSWORD}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_wrong_password_and_unknown_user_are_indistinguishable(csrf_client, user):
    client, token = csrf_client
    wrong = _login(client, token, user.email, "not-the-password")
    unknown = _login(client, token, "nobody@synthetic.test", PASSWORD)
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]
    assert AuditEvent.objects.filter(action=AuditAction.AUTH_LOGIN_FAILED).count() == 2


@pytest.mark.django_db
def test_inactive_user_cannot_sign_in(csrf_client, user):
    user.is_active = False
    user.save(update_fields=["is_active"])
    client, token = csrf_client
    assert _login(client, token, user.email, PASSWORD).status_code == 401


@pytest.mark.django_db
def test_login_is_rate_limited(csrf_client, user):
    client, token = csrf_client
    statuses = [_login(client, token, user.email, "wrong").status_code for _ in range(6)]
    assert statuses[-1] == 429


@pytest.mark.django_db
def test_logout_ends_session(csrf_client, user):
    client, token = csrf_client
    _login(client, token, user.email, PASSWORD)
    token = client.cookies["hims_csrftoken"].value  # rotated at login
    assert client.post("/api/v1/auth/logout/", HTTP_X_CSRFTOKEN=token).status_code == 204
    assert client.get("/api/v1/auth/me/").status_code == 401
