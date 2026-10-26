"""Automated test settings. Runs against real PostgreSQL (ADR-002), never SQLite."""

import os

os.environ.setdefault("HIMS_ENVIRONMENT", "test")
os.environ.setdefault("HIMS_DEPLOYMENT_ID", "test-deployment")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-insecure-key")
os.environ.setdefault("DATABASE_URL", "postgres://hims@localhost:5432/hims")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("REDIS_URL", "")

from common.environment import validate_environment

from .base import *  # noqa: F403
from .base import (
    DATABASES,
    HIMS_DATABASE_ENVIRONMENT,
    HIMS_DEPLOYMENT_ID,
    HIMS_ENVIRONMENT,
    REST_FRAMEWORK,
)

DEBUG = False
HIMS_ENABLE_ADMIN = True
ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # speed; tests only

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        "anon": "10000/min",
        "user": "10000/min",
        "login": "5/min",
        "invitation": "10000/min",
    },
}

# Tests drive outbox processing explicitly (or opt in to inline mode per test).
HIMS_OUTBOX_DISPATCH_INLINE = False
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
HIMS_APP_BASE_URL = "http://app.test"

LOGGING = {"version": 1, "disable_existing_loggers": False}

validate_environment(
    settings_profile="test",
    environment=HIMS_ENVIRONMENT,
    deployment_id=HIMS_DEPLOYMENT_ID,
    database_host=DATABASES["default"].get("HOST", ""),
    database_environment=HIMS_DATABASE_ENVIRONMENT,
    debug=DEBUG,
)
