"""The screens served by the same server as the API (spec 17, 31; HIMS-OPS-022)."""

import json
from pathlib import Path
from wsgiref.headers import Headers

import pytest
from django.conf import settings
from django.test import Client, override_settings

from common import screens

ROOT = Path(settings.BASE_DIR).parent
INDEX = b"<!doctype html><title>HIMS</title><div id='root'></div>"


@pytest.fixture
def built(tmp_path):
    (tmp_path / "index.html").write_bytes(INDEX)
    screens._index.cache_clear()
    with override_settings(HIMS_FRONTEND_DIST=str(tmp_path)):
        yield tmp_path
    screens._index.cache_clear()


def test_screens_send_the_same_headers_as_the_frontend_build():
    """One policy: what `vite preview` sends is what the server sends (HIMS-SEC-018)."""
    expected = json.loads((ROOT / "frontend" / "security-headers.json").read_text(encoding="utf-8"))
    assert expected == screens.SCREENS_HEADERS


@pytest.mark.django_db
def test_every_screen_address_gets_the_app_with_its_headers(built):
    client = Client()
    for path in ("/", "/staff", "/staff/0f0f0f0f/", "/audit/integrity"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.content == INDEX
        assert response["Cache-Control"] == "no-cache"
        assert (
            response["Content-Security-Policy"]
            == screens.SCREENS_HEADERS["Content-Security-Policy"]
        )
        assert response["X-Frame-Options"] == "DENY"


@pytest.mark.django_db
def test_the_servers_own_addresses_are_never_the_app(built):
    client = Client()
    assert client.get("/api/v1/no-such-thing/").status_code == 404
    assert client.get("/health/live/").status_code == 200
    assert client.get("/missing-file.js").status_code == 404
    assert client.get("/assets/missing-0000.js").status_code == 404
    # Django still adds the missing slash to the server's own addresses.
    assert client.get("/admin")["Location"] == "/admin/"
    assert client.get("/api/v1/facilities")["Location"] == "/api/v1/facilities/"


@pytest.mark.django_db
def test_nothing_is_served_when_the_screens_are_not_here():
    assert not settings.HIMS_FRONTEND_DIST  # a developer PC: Vite serves them
    assert Client().get("/").status_code == 404


@pytest.mark.django_db
def test_report_only_mode_is_followed(built):
    with override_settings(HIMS_CSP_REPORT_ONLY=True):
        response = Client().get("/staff")
    assert "Content-Security-Policy" not in response
    assert response["Content-Security-Policy-Report-Only"].startswith("default-src 'self'")


def test_files_get_the_right_caching_and_headers():
    page = Headers([])
    screens.add_headers(page, "/app/screens/index.html", "/index.html")
    assert page["Cache-Control"] == "no-cache"
    assert page["X-Frame-Options"] == "DENY"
    assert page["Strict-Transport-Security"] is None  # sent by Django, over HTTPS only
    asset = Headers([("Cache-Control", "max-age=60")])
    screens.add_headers(asset, "/app/screens/assets/a.js", "/assets/index-abc123.js")
    assert asset.get_all("Cache-Control") == ["public, max-age=31536000, immutable"]


def test_hosted_image_builds_the_screens_and_keeps_secrets_out():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "npm ci" in dockerfile and "npm run build" in dockerfile
    assert "COPY --from=screens --chown=hims:hims /screens/dist /app/screens" in dockerfile
    assert "HIMS_FRONTEND_DIST=/app/screens" in dockerfile
    collect = dockerfile.index("config.settings.build python manage.py collectstatic --noinput")
    assert collect < dockerfile.index("USER hims")  # collected before root is dropped
    assert "--require-hashes" in dockerfile
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    for secret in ("**/.env", "**/.env.*", "login.md", ".git"):
        assert secret in ignored, secret
