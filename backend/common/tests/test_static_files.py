"""Static files served by the app itself in hosted environments (HIMS-OPS-010; spec 6.2, 17).

The admin console's and API docs' files are collected and fingerprinted when the image is built,
then served by WhiteNoise: compressed, cached for a year by name. Swagger UI comes from the
installed sidecar package: nothing is loaded from another site and no inline script runs.
"""

import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import clear_url_caches

from common.security_headers import API_DOCS_POLICY

BACKEND = Path(__file__).resolve().parents[2]
HOSTED = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}


@pytest.fixture
def collected(settings, tmp_path):
    """The files collected exactly as the image build does, served by WhiteNoise."""
    settings.STORAGES = HOSTED
    settings.STATIC_ROOT = tmp_path / "staticfiles"
    # As in production.py: WhiteNoise right after Django's security middleware.
    settings.MIDDLEWARE = [
        settings.MIDDLEWARE[0],
        "whitenoise.middleware.WhiteNoiseMiddleware",
        *settings.MIDDLEWARE[1:],
    ]
    call_command("collectstatic", "--noinput", verbosity=0)
    return json.loads((settings.STATIC_ROOT / "staticfiles.json").read_text())["paths"]


@pytest.fixture
def api_docs(settings):
    """config.urls with the API docs switched on (they are off unless HIMS_ENABLE_API_DOCS)."""
    import config.urls

    settings.HIMS_ENABLE_API_DOCS = True
    importlib.reload(config.urls)
    clear_url_caches()
    yield
    settings.HIMS_ENABLE_API_DOCS = False
    importlib.reload(config.urls)
    clear_url_caches()


def test_collected_files_are_fingerprinted_and_compressed(collected, settings):
    assert re.fullmatch(r"admin/css/base\.[0-9a-f]{12}\.css", collected["admin/css/base.css"])
    swagger = "drf_spectacular_sidecar/swagger-ui-dist/swagger-ui-bundle.js"
    assert swagger in collected
    assert (settings.STATIC_ROOT / f"{collected['admin/css/base.css']}.gz").is_file()


@pytest.mark.django_db
def test_files_are_served_by_the_app_cached_for_a_year(collected):
    client = Client()  # created after collecting, so WhiteNoise sees the files
    css = client.get(f"/static/{collected['admin/css/base.css']}", HTTP_ACCEPT_ENCODING="gzip")
    assert css.status_code == 200
    assert "max-age=315360000" in css["Cache-Control"] and "immutable" in css["Cache-Control"]
    assert css["Content-Encoding"] == "gzip"
    assert client.get("/static/admin/css/no-such-file.css").status_code == 404


@pytest.mark.django_db
def test_admin_pages_link_the_fingerprinted_files(collected):
    page = Client().get("/admin/login/").content.decode()
    assert f"/static/{collected['admin/css/base.css']}" in page


@pytest.mark.django_db
def test_api_docs_load_nothing_from_other_sites_and_run_no_inline_script(api_docs):
    client = Client()
    response = client.get("/api/docs/")
    assert response.status_code == 200
    page = response.content.decode()
    assert "cdn.jsdelivr" not in page and "https://" not in page
    assert "/static/drf_spectacular_sidecar/swagger-ui-dist/swagger-ui-bundle.js" in page
    scripts = re.findall(r"<script([^>]*)>(.*?)</script>", page, flags=re.DOTALL)
    assert scripts and all("src=" in attrs and not body.strip() for attrs, body in scripts)
    assert response["Content-Security-Policy"] == API_DOCS_POLICY
    start = client.get("/api/docs/", {"script": ""})
    assert start.status_code == 200 and "javascript" in start["Content-Type"]


def test_api_docs_policy_allows_only_this_site():
    assert "http" not in API_DOCS_POLICY
    script_src = next(p for p in API_DOCS_POLICY.split(";") if "script-src" in p)
    assert script_src.strip() == "script-src 'self'"


def test_image_build_collects_the_files_before_dropping_root():
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    collect = dockerfile.index("config.settings.build python manage.py collectstatic --noinput")
    assert collect < dockerfile.index("USER hims")
    assert "staticfiles" in (BACKEND / ".dockerignore").read_text(encoding="utf-8")


def _setting_in(settings_module: str, expression: str, extra_env: dict) -> str:
    env = {
        **{k: v for k, v in os.environ.items() if k != "DATABASE_URL"},
        "DJANGO_SETTINGS_MODULE": settings_module,
        "HIMS_ENV_FILE": "__no_env_file__",
        **extra_env,
    }
    for name in ("HIMS_MIGRATION_DATABASE_URL", "HIMS_ENVIRONMENT", "HIMS_DEPLOYMENT_ID"):
        if name not in extra_env:
            env.pop(name, None)
    script = f"import django; django.setup(); from django.conf import settings; print({expression})"
    result = subprocess.run(  # noqa: S603 - fixed interpreter and script
        [sys.executable, "-c", script], cwd=BACKEND, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr[-800:]
    return result.stdout.strip().splitlines()[-1]


def test_image_build_settings_need_no_secrets_or_database():
    storage = _setting_in(
        "config.settings.build", "settings.STORAGES['staticfiles']['BACKEND']", {}
    )
    assert storage == HOSTED["staticfiles"]["BACKEND"]


def test_production_serves_the_fingerprinted_files():
    production = {
        "HIMS_ENVIRONMENT": "staging",
        "HIMS_DATABASE_ENVIRONMENT": "staging",
        "HIMS_DEPLOYMENT_ID": "static-test",
        "DJANGO_SECRET_KEY": "x" * 50,
        "DJANGO_ALLOWED_HOSTS": "static.invalid",
        "HIMS_FIELD_ENCRYPTION_KEYS": "Zm9vYmFyZm9vYmFyZm9vYmFyZm9vYmFyZm9vYmFyMTI=",
        "HIMS_AUDIT_CHAIN_KEYS": "ci:" + "a" * 64,
        "HIMS_TRUSTED_PROXIES": "10.0.0.0/8",
        "DATABASE_URL": "postgres://u:p@db.static.invalid:5432/hims",
        "HIMS_ACCEPT_LOCAL_DOCUMENT_STORAGE": "true",
    }
    middleware = _setting_in("config.settings.production", "settings.MIDDLEWARE[1]", production)
    assert middleware == "whitenoise.middleware.WhiteNoiseMiddleware"
    storage = _setting_in(
        "config.settings.production", "settings.STORAGES['staticfiles']['BACKEND']", production
    )
    assert storage == HOSTED["staticfiles"]["BACKEND"]
