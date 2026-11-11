"""Settings for every managed environment: Development, QA, Staging and Production.

The same immutable image runs in all four (spec 31.5, 33.3); only environment variables and
secrets differ. HIMS_ENVIRONMENT selects which managed environment this process belongs to.
"""

from django.core.exceptions import ImproperlyConfigured

from common.client_ip import validate_console_networks, validate_trusted_proxies
from common.environment import validate_environment

from .base import *  # noqa: F403
from .base import (
    DATABASES,
    DEBUG,
    EMAIL_BACKEND,
    HIMS_ADMIN_ALLOWED_NETWORKS,
    HIMS_AUDIT_CHAIN_KEYS,
    HIMS_CONFIRM_IDENTITY_MINUTES,
    HIMS_DATABASE_ENVIRONMENT,
    HIMS_DEPLOYMENT_ID,
    HIMS_ENABLE_ADMIN,
    HIMS_ENVIRONMENT,
    HIMS_FIELD_ENCRYPTION_KEYS,
    HIMS_FRONTEND_DIST,
    HIMS_MFA_REQUIRED_FOR_PRIVILEGED,
    HIMS_SESSION_MAX_SECONDS,
    HIMS_TRUSTED_PROXIES,
    HOSTED_STORAGES,
    MIDDLEWARE,
    SESSION_COOKIE_AGE,
    env,
)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# Preload is hard to undo and is the customer domain owner's decision, so it is opt-in.
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=False)
SILENCED_SYSTEM_CHECKS = [] if SECURE_HSTS_PRELOAD else ["security.W021"]
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_REDIRECT_EXEMPT = [r"^health/"]  # ALB health checks arrive over HTTP
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"
# Static files collected at image build, served by the app itself with WhiteNoise, right after
# Django's security middleware (HIMS-OPS-010). On a developer PC runserver serves them instead.
STORAGES = HOSTED_STORAGES
# The screens from the same server (HIMS-OPS-022): WhiteNoise serves the built app's files at the
# site root, with the screens' protection headers; screen addresses get index.html (config/urls).
if HIMS_FRONTEND_DIST:
    from common.screens import add_headers as _screens_headers

    WHITENOISE_ROOT = HIMS_FRONTEND_DIST
    WHITENOISE_ADD_HEADERS_FUNCTION = _screens_headers
MIDDLEWARE = [MIDDLEWARE[0], "whitenoise.middleware.WhiteNoiseMiddleware", *MIDDLEWARE[1:]]

# Secrets never reach a log (HIMS-SEC-019): a printed email lands in the server log here, so it
# is printed with sign-in links and codes hidden.
if EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
    EMAIL_BACKEND = "apps.notifications.backends.ConsoleEmailBackend"

if not HIMS_FIELD_ENCRYPTION_KEYS:
    raise ImproperlyConfigured("HIMS_FIELD_ENCRYPTION_KEYS must be set (from the secret manager).")
if HIMS_ENVIRONMENT == "production" and not HIMS_MFA_REQUIRED_FOR_PRIVILEGED:
    raise ImproperlyConfigured(
        "Two-factor sign-in for privileged users cannot be disabled in production."
    )
if not HIMS_AUDIT_CHAIN_KEYS:
    raise ImproperlyConfigured("HIMS_AUDIT_CHAIN_KEYS must be set (from the secret manager).")
for _entry in HIMS_AUDIT_CHAIN_KEYS:
    _key_id, _, _secret = _entry.partition(":")
    if not _key_id or len(_key_id) > 32 or len(_secret) < 32:
        raise ImproperlyConfigured(
            "Each HIMS_AUDIT_CHAIN_KEYS entry must look like 'key-id:secret' "
            "(id up to 32 characters, secret at least 32 characters)."
        )

if not 60 * 60 <= HIMS_SESSION_MAX_SECONDS <= 24 * 60 * 60:
    raise ImproperlyConfigured("HIMS_SESSION_MAX_SECONDS must be between 1 and 24 hours.")
if not 5 * 60 <= SESSION_COOKIE_AGE <= 60 * 60:
    raise ImproperlyConfigured("HIMS_SESSION_IDLE_SECONDS must be between 5 and 60 minutes.")
if not 1 <= HIMS_CONFIRM_IDENTITY_MINUTES <= 60:
    raise ImproperlyConfigured("HIMS_CONFIRM_IDENTITY_MINUTES must be between 1 and 60.")
if not HIMS_TRUSTED_PROXIES:
    raise ImproperlyConfigured(
        "HIMS_TRUSTED_PROXIES must list the load balancer's network: without it every audit "
        "record and rate limit would see the load balancer's address, not the person's."
    )
try:
    validate_trusted_proxies(HIMS_TRUSTED_PROXIES)
except ValueError as exc:
    raise ImproperlyConfigured(f"HIMS_TRUSTED_PROXIES has a bad entry: {exc}") from exc
# The console answers only listed addresses (HIMS-SEC-015, ADR-016): with it switched on, the
# list must name the office or VPN network, never every address.
if HIMS_ENABLE_ADMIN and not HIMS_ADMIN_ALLOWED_NETWORKS:
    raise ImproperlyConfigured(
        "HIMS_ADMIN_ALLOWED_NETWORKS must list the networks the admin console may be used from "
        "(for example the office or VPN network) when HIMS_ENABLE_ADMIN is on."
    )
try:
    validate_console_networks(HIMS_ADMIN_ALLOWED_NETWORKS)
except ValueError as exc:
    raise ImproperlyConfigured(f"HIMS_ADMIN_ALLOWED_NETWORKS has a bad entry: {exc}") from exc

validate_environment(
    settings_profile="production",
    environment=HIMS_ENVIRONMENT,
    deployment_id=HIMS_DEPLOYMENT_ID,
    database_host=DATABASES["default"].get("HOST", ""),
    database_environment=HIMS_DATABASE_ENVIRONMENT,
    debug=DEBUG,
)
