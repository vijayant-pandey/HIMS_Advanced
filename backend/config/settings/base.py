"""Settings shared by every environment.

All configuration comes from the environment (spec 31.4). Environment-specific modules
(local, test, production) only adjust behaviour; they never hard-code credentials.
"""

import os
import sys
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

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
# Tracing (spec 6, 18; HIMS-PLAT-016; common/tracing.py): none (default) | console | otlp.
# For otlp, set the standard OTEL_EXPORTER_OTLP_ENDPOINT (and headers) for the collector.
HIMS_TRACING_EXPORTER = env.str("HIMS_TRACING_EXPORTER", default="none").strip().lower()
if HIMS_TRACING_EXPORTER not in ("none", "console", "otlp"):
    raise ImproperlyConfigured("HIMS_TRACING_EXPORTER must be none, console or otlp.")
# Share of requests traced (0.0 to 1.0). A request that arrives already traced keeps its choice.
HIMS_TRACING_SAMPLE_RATIO = env.float("HIMS_TRACING_SAMPLE_RATIO", default=1.0)
if not 0.0 <= HIMS_TRACING_SAMPLE_RATIO <= 1.0:
    raise ImproperlyConfigured("HIMS_TRACING_SAMPLE_RATIO must be between 0.0 and 1.0.")

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
    "django.contrib.postgres",  # range types and no-overlap constraints (rotas)
    "rest_framework",
    "drf_spectacular",
    "drf_spectacular_sidecar",  # Swagger UI files served by HIMS itself, no CDN (HIMS-OPS-010)
    # Shared platform services
    "common.idempotency",
    "common.outbox",
    "common.datadict",  # generates the data dictionary (spec 28); no tables
    "common.devtools",  # developer/test-only commands (browser-test database); no tables
    # Business domains
    "apps.audit",
    "apps.organizations",
    "apps.identity",
    "apps.facilities",
    "apps.access_control",
    "apps.staff",
    "apps.beds",
    "apps.equipment",
    "apps.numbering",
    "apps.features",
    "apps.notifications",
    "apps.compliance",
    "apps.rosters",
    "apps.recovery",
]

# Django admin is the HIMS operations console (ADR-016): gated by HIMS RBAC rather than
# is_staff/is_superuser, every change audited, deletion disabled, and domain rules reused from
# services. It is exposed only where HIMS_ENABLE_ADMIN is true (default: local only).
HIMS_ENABLE_ADMIN = env.bool("HIMS_ENABLE_ADMIN", default=False)
# Addresses or networks the console answers (HIMS-SEC-015), checked against the real client
# address on every console page, before sign-in. Anyone else gets "Not found". Empty means
# nobody; a developer PC defaults to this computer only. Hosted environments refuse to start
# with the console on and no list. A firewall rule in front of the server comes with hosting.
HIMS_ADMIN_ALLOWED_NETWORKS = env.list("HIMS_ADMIN_ALLOWED_NETWORKS", default=[])

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "common.security_headers.SecurityHeadersMiddleware",
    "common.request_context.RequestContextMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Before CommonMiddleware, so "/admin" is not redirected to "/admin/" for a refused address.
    "common.admin.allowed_addresses.ConsoleAddressMiddleware",
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

# --- Separate database users (HIMS-OPS-007; spec 13.2, 17.2, 30.5) ------------------------------
# DATABASE_URL is the app's own limited user. The owner's credentials are used only by commands
# that change the schema or need the owner's rights; in hosted environments the migration job
# gets them as its DATABASE_URL instead. See docs/workflows/database-users.md.
HIMS_MIGRATION_DATABASE_URL = env.str("HIMS_MIGRATION_DATABASE_URL", default="")
OWNER_COMMANDS = frozenset({"migrate", "setup_database_roles", "flush", "createcachetable"})
if HIMS_MIGRATION_DATABASE_URL and len(sys.argv) > 1 and sys.argv[1] in OWNER_COMMANDS:
    _app_database = DATABASES["default"]
    DATABASES["default"] = {
        **_app_database,
        **env.db_url("HIMS_MIGRATION_DATABASE_URL"),
        "OPTIONS": _app_database["OPTIONS"],
    }
# Backups and restore drills (HIMS-OPS-009) need the owner's rights (they create a database).
HIMS_OWNER_DATABASE = (
    {**DATABASES["default"], **env.db_url("HIMS_MIGRATION_DATABASE_URL")}
    if HIMS_MIGRATION_DATABASE_URL
    else None
)
# Names of the database users; empty means hims_<deployment>_app / _readonly / _breakglass.
HIMS_DB_APP_ROLE = env.str("HIMS_DB_APP_ROLE", default="")
HIMS_DB_READONLY_ROLE = env.str("HIMS_DB_READONLY_ROLE", default="")
HIMS_DB_BREAKGLASS_ROLE = env.str("HIMS_DB_BREAKGLASS_ROLE", default="")

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
# Hosted environments (HIMS-OPS-010): the admin console and API docs files are collected into the
# image at build time (config/settings/build.py) and served by WhiteNoise (added to the middleware
# in production.py), compressed, with fingerprinted names browsers may cache for a year. On a
# developer PC runserver serves them, as before.
HOSTED_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

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
# Longest cover arrangement (delegated access, HIMS-IAM-017), in days. Arrange a new one after.
HIMS_DELEGATION_MAX_DAYS = env.int("HIMS_DELEGATION_MAX_DAYS", default=30)
# Tamper evidence for the audit log (HIMS-SEC-010, ADR-013). Keys for the keyed chain hash as
# "key-id:secret", newest first; keep older keys listed so older links can still be checked.
# They live outside the database (secret manager), so someone with database access alone
# cannot rebuild the chain. Required in managed environments; developer machines and tests
# fall back to a key derived from DJANGO_SECRET_KEY. See apps/audit/integrity.py.
HIMS_AUDIT_CHAIN_KEYS = env.list("HIMS_AUDIT_CHAIN_KEYS", default=[])
# Our own proxies (addresses or networks): X-Forwarded-For is believed only from these
# (common/client_ip.py, HIMS-SEC-014). Empty means never believed.
HIMS_TRUSTED_PROXIES = env.list("HIMS_TRUSTED_PROXIES", default=[])
# True only tells browsers to report instead of block: a switch for rolling out or
# backing out a policy change (HIMS-SEC-012).
HIMS_CSP_REPORT_ONLY = env.bool("HIMS_CSP_REPORT_ONLY", default=False)
# How long a person stays confirmed before being asked again for a sensitive action
# (apps/identity/confirmation.py, HIMS-IAM-007).
HIMS_CONFIRM_IDENTITY_MINUTES = env.int("HIMS_CONFIRM_IDENTITY_MINUTES", default=15)
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
        "common.throttling.AnonThrottle",
        "common.throttling.UserThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env.str("HIMS_THROTTLE_ANON", default="60/min"),
        "user": env.str("HIMS_THROTTLE_USER", default="1200/min"),
        "login": env.str("HIMS_THROTTLE_LOGIN", default="10/min"),
        "invitation": env.str("HIMS_THROTTLE_INVITATION", default="20/min"),
        "password_reset": env.str("HIMS_THROTTLE_PASSWORD_RESET", default="5/min"),
        "browser_report": env.str("HIMS_THROTTLE_BROWSER_REPORT", default="30/min"),
        "confirm_identity": env.str("HIMS_THROTTLE_CONFIRM_IDENTITY", default="10/min"),
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
    # Swagger UI from the installed sidecar package, never a CDN (HIMS-OPS-010).
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
    "ENUM_NAME_OVERRIDES": {
        "OrganizationStatusEnum": "apps.organizations.models.Organization.Status",
        "ActiveStatusEnum": "apps.facilities.models.Facility.Status",
        "DesignationCategoryEnum": "apps.staff.models.Designation.Category",
        "QualificationTypeCategoryEnum": "apps.staff.models.QualificationType.Category",
        "OutcomeEnum": "apps.audit.models.AuditEvent.Outcome",
        "IntegrityOutcomeEnum": "apps.audit.models.AuditIntegrityCheck.Outcome",
        "TriggerEnum": "apps.audit.models.AuditIntegrityCheck.Trigger",
        "DelegationStatusEnum": "apps.access_control.models.AccessDelegation.Status",
        "ComplianceStatusEnum": "apps.compliance.models.ComplianceRequirement.Status",
        "RiskStatusEnum": "apps.compliance.models.RiskEntry.Status",
        "IncidentStatusEnum": "apps.compliance.models.SecurityIncident.Status",
        "IncidentNotificationStatusEnum": "apps.compliance.models.IncidentNotification.Status",
        "ShiftKindEnum": "apps.rosters.models.ShiftType.Kind",
        "ShiftStatusEnum": "apps.rosters.models.Shift.Status",
        "LeaveStatusEnum": "apps.rosters.models.LeaveRequest.Status",
        "RestoreDrillOutcomeEnum": "apps.recovery.models.RestoreDrill.Outcome",
        "RestoreDrillTriggerEnum": "apps.recovery.models.RestoreDrill.Trigger",
        "EquipmentCategoryEnum": "apps.equipment.models.Equipment.Category",
        "EquipmentStatusEnum": "apps.equipment.models.Equipment.Status",
        "EquipmentServiceKindEnum": "apps.equipment.models.EquipmentServiceRecord.Kind",
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
# Clean-up (HIMS-PLAT-014): published and dismissed events, and their duplicate-check markers,
# are deleted after this many days. Waiting and failed events are never deleted automatically.
HIMS_OUTBOX_RETENTION_DAYS = env.int("HIMS_OUTBOX_RETENTION_DAYS", default=30)
# An event still waiting after this many minutes is "stuck" and needs a look (runbook).
HIMS_OUTBOX_STUCK_MINUTES = env.int("HIMS_OUTBOX_STUCK_MINUTES", default=15)

# --- Invitations and email (HIMS-IAM-003) ------------------------------------------------
# Public URL of this deployment's React app; activation links point here.
HIMS_APP_BASE_URL = env.str("HIMS_APP_BASE_URL", default="http://localhost:5175")
HIMS_INVITATION_TTL_HOURS = env.int("HIMS_INVITATION_TTL_HOURS", default=72)
HIMS_PASSWORD_RESET_TTL_MINUTES = env.int("HIMS_PASSWORD_RESET_TTL_MINUTES", default=60)
HIMS_PASSWORD_RESET_MAX_PER_HOUR = env.int("HIMS_PASSWORD_RESET_MAX_PER_HOUR", default=3)
# Console backend prints emails to the backend output. A real provider (e.g. Amazon SES)
# is configured per environment before go-live (HIMS-OPS-011).
EMAIL_BACKEND = env.str(
    "DJANGO_EMAIL_BACKEND", default="apps.notifications.backends.ConsoleEmailBackend"
)
if EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
    EMAIL_BACKEND = "apps.notifications.backends.ConsoleEmailBackend"
DEFAULT_FROM_EMAIL = env.str("DJANGO_DEFAULT_FROM_EMAIL", default="HIMS <no-reply@hims.invalid>")
# SMTP (e.g. Gmail with an app password, or Amazon SES) when DJANGO_EMAIL_BACKEND is
# django.core.mail.backends.smtp.EmailBackend. See docs/workflows/notifications.md.
EMAIL_HOST = env.str("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env.str("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env.str("EMAIL_HOST_PASSWORD", default="")
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=20)
# SMS (HIMS-NOTIF-001): printed to the server output until an SMS provider is chosen.
HIMS_SMS_BACKEND = env.str(
    "HIMS_SMS_BACKEND", default="apps.notifications.backends.ConsoleSmsBackend"
)
# A failed email/SMS is retried after 5, 15, 60 and 240 minutes, then given up.
HIMS_NOTIFICATION_MAX_ATTEMPTS = env.int("HIMS_NOTIFICATION_MAX_ATTEMPTS", default=5)
# Folder for django.core.mail.backends.filebased.EmailBackend: browser tests read invitation and
# reset links from here (HIMS-QA-001). Unused with any other email backend.
if env.str("HIMS_EMAIL_FILE_PATH", default=""):
    EMAIL_FILE_PATH = env.str("HIMS_EMAIL_FILE_PATH")

# --- Two-factor sign-in and field encryption (HIMS-IAM-005; spec 4.4, 13.1, 13.3) -----------
# Users holding any permission in access_control.catalog.MFA_REQUIRED_PERMISSIONS must use
# two-factor sign-in. Can be relaxed on a developer machine; production refuses to start without it.
HIMS_MFA_REQUIRED_FOR_PRIVILEGED = env.bool("HIMS_MFA_REQUIRED_FOR_PRIVILEGED", default=True)
# Optionally require two-factor for every user, not only privileged ones.
HIMS_MFA_REQUIRED_FOR_ALL = env.bool("HIMS_MFA_REQUIRED_FOR_ALL", default=False)
# Fernet keys (newest first) encrypting authenticator secrets; see common/crypto.py.
HIMS_FIELD_ENCRYPTION_KEYS = env.list("HIMS_FIELD_ENCRYPTION_KEYS", default=[])
HIMS_IDEMPOTENCY_RETENTION_HOURS = env.int("HIMS_IDEMPOTENCY_RETENTION_HOURS", default=48)

# --- Backups and restore drills (HIMS-OPS-009; spec 13.5, 17.3, 27.1) ----------------------
# Only on a developer PC: hosted environments use the cloud database service's backups.
# Backups hold every record (incl. password hashes): keep the folder private and out of git.
HIMS_BACKUP_DIR = env.path("HIMS_BACKUP_DIR", default=BASE_DIR / "backups" / HIMS_DEPLOYMENT_ID)
# Where pg_dump/pg_restore are (see apps/recovery/pg_tools.py); found automatically if empty.
HIMS_PG_BIN_DIR = env.str("HIMS_PG_BIN_DIR", default="")
# Run the tools inside this database container instead (docker-compose, CI).
HIMS_PG_DOCKER_CONTAINER = env.str("HIMS_PG_DOCKER_CONTAINER", default="")
# A passed restore drill older than this is shown as overdue.
HIMS_RESTORE_DRILL_INTERVAL_DAYS = env.int("HIMS_RESTORE_DRILL_INTERVAL_DAYS", default=90)

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
