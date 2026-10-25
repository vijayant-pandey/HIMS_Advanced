"""Developer workstation settings. Synthetic data only (spec 31.1)."""

from common.environment import validate_environment

from .base import *  # noqa: F403
from .base import (
    DATABASES,
    HIMS_DATABASE_ENVIRONMENT,
    HIMS_DEPLOYMENT_ID,
    HIMS_ENVIRONMENT,
    REST_FRAMEWORK,
    env,
)

DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS", default=["http://localhost:5173", "http://127.0.0.1:5173"]
)
HIMS_ENABLE_API_DOCS = env.bool("HIMS_ENABLE_API_DOCS", default=True)
HIMS_ENABLE_ADMIN = env.bool("HIMS_ENABLE_ADMIN", default=True)

REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

validate_environment(
    settings_profile="local",
    environment=HIMS_ENVIRONMENT,
    deployment_id=HIMS_DEPLOYMENT_ID,
    database_host=DATABASES["default"].get("HOST", ""),
    database_environment=HIMS_DATABASE_ENVIRONMENT,
    debug=DEBUG,
)
