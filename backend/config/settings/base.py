"""Settings shared by every environment.

All configuration comes from the environment (spec 31.4). Environment-specific modules
(local, test, production) only adjust behaviour; they never hard-code credentials.
"""

import os
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# HIMS_ENV_FILE selects which local deployment to run (e.g. ".env.us" for a second hospital on
# the same machine). Real environment variables always win over the file.
_env_file = BASE_DIR / os.environ.get("HIMS_ENV_FILE", ".env")
if _env_file.exists():
    environ.Env.read_env(_env_file, overwrite=False)

# --- Deployment identity -----------------------------------------------------------------
# One deployment serves exactly one hospital organization (ADR-003, ADR-009).
HIMS_ENVIRONMENT = env.str("HIMS_ENVIRONMENT")
HIMS_DEPLOYMENT_ID = env.str("HIMS_DEPLOYMENT_ID")
HIMS_RELEASE = env.str("HIMS_RELEASE", default="unversioned")

SECRET_KEY = env.str("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# --- Applications ------------------------------------------------------------------------
INSTALLED_APPS = [
    "common.admin.apps.HimsAdminConfig",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    # Shared platform services
    "common.idempotency",
    "common.outbox",
    # Business domains
    "apps.audit",
    "apps.organizations",
    "apps.identity",
    "apps.facilities",
    "apps.access_control",
    "apps.staff",
    "apps.beds",
    "apps.numbering",
    "apps.features",
]

# Django admin is the HIMS operations console (ADR-016): gated by HIMS RBAC rather than
# is_staff/is_superuser, every change audited, deletion disabled, and domain rules reused from
# services. It is exposed only where HIMS_ENABLE_ADMIN is true (default: local only).
HIMS_ENABLE_ADMIN = env.bool("HIMS_ENABLE_ADMIN", default=False)

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "common.request_context.RequestContextMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],  # admin look-and-feel overrides
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "common.theming.theme_context",
            ]
        },
    }
]

# --- Database ----------------------------------------------------------------------------
# PostgreSQL is authoritative in every environment (ADR-002).
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False  # services own their transaction boundaries
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"].setdefault("OPTIONS", {})["application_name"] = (
    f"hims-{HIMS_DEPLOYMENT_ID}-{HIMS_ENVIRONMENT}"
)
HIMS_DATABASE_ENVIRONMENT = env.str("HIMS_DATABASE_ENVIRONMENT", default=None)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Cache (Redis is never a source of truth: ADR-004) -----------------------------------
REDIS_URL = env.str("REDIS_URL", default="")
_cache_prefix = f"hims:{HIMS_DEPLOYMENT_ID}:{HIMS_ENVIRONMENT}"  # key isolation (spec 7.4)
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "KEY_PREFIX": _cache_prefix,
            "TIMEOUT": 300,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "KEY_PREFIX": _cache_prefix,
        }
    }

# --- Identity and sessions (ADR-011) -----------------------------------------------------
AUTH_USER_MODEL = "identity.User"
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Database-backed sessions so that revocation (logout, suspension, termination) is immediate.
SESSION_ENGINE = "django.contrib.sessions.backends.db"
# Configurable so several deployments on one host (local dev ports) do not share cookies.
SESSION_COOKIE_NAME = env.str("HIMS_SESSION_COOKIE_NAME", default="hims_session")
SESSION_COOKIE_AGE = env.int("HIMS_SESSION_IDLE_SECONDS", default=30 * 60)
SESSION_SAVE_EVERY_REQUEST = True  # sliding idle timeout
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_NAME = env.str("HIMS_CSRF_COOKIE_NAME", default="hims_csrftoken")
CSRF_COOKIE_HTTPONLY = False  # the SPA must read it to send X-CSRFToken
CSRF_COOKIE_SAMESITE = "Lax"

# --- Internationalisation ----------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"  # instants are stored in UTC; facility time zone is applied for display
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Uploaded documents (HIMS-STAFF-005, spec 4.22; ADR-020) -------------------------------
# Never served from a public URL: files are downloaded only through the API, after a
# permission check, and every download is audited. One folder per deployment keeps hospitals
# that share a machine apart. Production must use S3-compatible storage (see ADR-020); local
# disk on hosts like Render is not durable.
MEDIA_ROOT = env.path("HIMS_MEDIA_ROOT", default=BASE_DIR / "media" / HIMS_DEPLOYMENT_ID)
MEDIA_URL = "/media-not-served/"
HIMS_UPLOAD_MAX_BYTES = env.int("HIMS_UPLOAD_MAX_BYTES", default=10 * 1024 * 1024)
# Only for throw-away runs (CI image smoke test, short demos): accept that uploaded files on the
# server's own disk are lost on the next deploy. Never set this for a real hospital.
HIMS_ACCEPT_LOCAL_DOCUMENT_STORAGE = env.bool("HIMS_ACCEPT_LOCAL_DOCUMENT_STORAGE", default=False)
# Days before expiry at which HR and the person are warned (and again once expired).
HIMS_CREDENTIAL_ALERT_DAYS = env.list("HIMS_CREDENTIAL_ALERT_DAYS", cast=int, default=[60, 30, 7])
# Periodic access review (HIMS-IAM-012): how often a full review is due, and how long one runs.
HIMS_ACCESS_REVIEW_INTERVAL_DAYS = env.int("HIMS_ACCESS_REVIEW_INTERVAL_DAYS", default=90)
HIMS_ACCESS_REVIEW_DEFAULT_DAYS_TO_FINISH = 14
# Tamper evidence for the audit log (HIMS-SEC-010, ADR-013). Keys for the keyed chain hash as
# "key-id:secret", newest first; keep older keys listed so older links can still be checked.
# They live outside the database (secret manager), so someone with database access alone
# cannot rebuild the chain. Required in managed environments; developer machines and tests
# fall back to a key derived from DJANGO_SECRET_KEY. See apps/audit/integrity.py.
HIMS_AUDIT_CHAIN_KEYS = env.list("HIMS_AUDIT_CHAIN_KEYS", default=[])
# Sealing also picks up events written up to this long before its last run (a slow transaction
# commits late). Older events that are not in the chain are reported by the integrity check.
HIMS_AUDIT_SEAL_LOOKBACK_HOURS = env.int("HIMS_AUDIT_SEAL_LOOKBACK_HOURS", default=24)

# --- REST API (spec 16, 29) --------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["common.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["common.permissions.ScopedPermission"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PAGINATION_CLASS": "common.pagination.StandardPagination",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "common.exceptions.handler.problem_details_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env.str("HIMS_THROTTLE_ANON", default="60/min"),
        "user": env.str("HIMS_THROTTLE_USER", default="1200/min"),
        "login": env.str("HIMS_THROTTLE_LOGIN", default="10/min"),
        "invitation": env.str("HIMS_THROTTLE_INVITATION", default="20/min"),
        "password_reset": env.str("HIMS_THROTTLE_PASSWORD_RESET", default="5/min"),
    },
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "HIMS API",
    "DESCRIPTION": "Hospital Information Management System REST API (v1).",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "ENUM_NAME_OVERRIDES": {
        "OrganizationStatusEnum": "apps.organizations.models.Organization.Status",
        "ActiveStatusEnum": "apps.facilities.models.Facility.Status",
        "DesignationCategoryEnum": "apps.staff.models.Designation.Category",
        "QualificationTypeCategoryEnum": "apps.staff.models.QualificationType.Category",
        "OutcomeEnum": "apps.audit.models.AuditEvent.Outcome",
        "IntegrityOutcomeEnum": "apps.audit.models.AuditIntegrityCheck.Outcome",
    },
}
HIMS_ENABLE_API_DOCS = env.bool("HIMS_ENABLE_API_DOCS", default=False)

# Base URI for RFC 9457 problem "type" values (spec 29.2).
HIMS_PROBLEM_TYPE_BASE = env.str(
    "HIMS_PROBLEM_TYPE_BASE", default="https://errors.hims.invalid/problems/"
)

# --- Celery (spec 14; ADR-010) -----------------------------------------------------------
CELERY_BROKER_URL = env.str("CELERY_BROKER_URL", default=REDIS_URL or "memory://")
CELERY_TASK_DEFAULT_QUEUE = f"{HIMS_DEPLOYMENT_ID}.default"
HIMS_CELERY_QUEUE_PREFIX = HIMS_DEPLOYMENT_ID

# --- Platform services -------------------------------------------------------------------
HIMS_OUTBOX_BATCH_SIZE = env.int("HIMS_OUTBOX_BATCH_SIZE", default=100)
HIMS_OUTBOX_MAX_ATTEMPTS = env.int("HIMS_OUTBOX_MAX_ATTEMPTS", default=12)
# Without a broker (local development) events are processed in-process after commit.
HIMS_OUTBOX_DISPATCH_INLINE = env.bool("HIMS_OUTBOX_DISPATCH_INLINE", default=not REDIS_URL)

# --- Invitations and email (HIMS-IAM-003) ------------------------------------------------
# Public URL of this deployment's React app; activation links point here.
HIMS_APP_BASE_URL = env.str("HIMS_APP_BASE_URL", default="http://localhost:5175")
HIMS_INVITATION_TTL_HOURS = env.int("HIMS_INVITATION_TTL_HOURS", default=72)
HIMS_PASSWORD_RESET_TTL_MINUTES = env.int("HIMS_PASSWORD_RESET_TTL_MINUTES", default=60)
HIMS_PASSWORD_RESET_MAX_PER_HOUR = env.int("HIMS_PASSWORD_RESET_MAX_PER_HOUR", default=3)
# Console backend prints emails to the backend output. A real provider (e.g. Amazon SES)
# is configured per environment before go-live (HIMS-OPS-011).
EMAIL_BACKEND = env.str(
    "DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = env.str("DJANGO_DEFAULT_FROM_EMAIL", default="HIMS <no-reply@hims.invalid>")

# --- Two-factor sign-in and field encryption (HIMS-IAM-005; spec 4.4, 13.1, 13.3) -----------
# Users holding any permission in access_control.catalog.MFA_REQUIRED_PERMISSIONS must use
# two-factor sign-in. Can be relaxed on a developer machine; production refuses to start without it.
HIMS_MFA_REQUIRED_FOR_PRIVILEGED = env.bool("HIMS_MFA_REQUIRED_FOR_PRIVILEGED", default=True)
# Optionally require two-factor for every user, not only privileged ones.
HIMS_MFA_REQUIRED_FOR_ALL = env.bool("HIMS_MFA_REQUIRED_FOR_ALL", default=False)
# Fernet keys (newest first) encrypting authenticator secrets; see common/crypto.py.
HIMS_FIELD_ENCRYPTION_KEYS = env.list("HIMS_FIELD_ENCRYPTION_KEYS", default=[])
HIMS_IDEMPOTENCY_RETENTION_HOURS = env.int("HIMS_IDEMPOTENCY_RETENTION_HOURS", default=48)

# --- Logging: structured, PHI-minimised (spec 13.4, 27.2) --------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_context": {"()": "common.request_context.RequestContextLogFilter"}},
    "formatters": {"json": {"()": "common.logging.JsonFormatter"}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["request_context"],
        }
    },
    "root": {"handlers": ["console"], "level": env.str("HIMS_LOG_LEVEL", default="INFO")},
    "loggers": {
        # Request logs can carry query strings; keep Django's own request logger quiet.
        "django.request": {"level": "ERROR"},
        "django.db.backends": {"level": "WARNING"},
    },
}
