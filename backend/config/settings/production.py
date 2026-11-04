"""Settings for every managed environment: Development, QA, Staging and Production.

The same immutable image runs in all four (spec 31.5, 33.3); only environment variables and
secrets differ. HIMS_ENVIRONMENT selects which managed environment this process belongs to.
"""

from django.core.exceptions import ImproperlyConfigured

from common.client_ip import validate_trusted_proxies
from common.environment import validate_environment

from .base import *  # noqa: F403
from .base import (
    DATABASES,
    DEBUG,
    HIMS_AUDIT_CHAIN_KEYS,
    HIMS_DATABASE_ENVIRONMENT,
    HIMS_DEPLOYMENT_ID,
    HIMS_ENVIRONMENT,
    HIMS_FIELD_ENCRYPTION_KEYS,
    HIMS_MFA_REQUIRED_FOR_PRIVILEGED,
    HIMS_TRUSTED_PROXIES,
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

if not HIMS_TRUSTED_PROXIES:
    raise ImproperlyConfigured(
        "HIMS_TRUSTED_PROXIES must list the load balancer's network: without it every audit "
        "record and rate limit would see the load balancer's address, not the person's."
    )
try:
    validate_trusted_proxies(HIMS_TRUSTED_PROXIES)
except ValueError as exc:
    raise ImproperlyConfigured(f"HIMS_TRUSTED_PROXIES has a bad entry: {exc}") from exc

validate_environment(
    settings_profile="production",
    environment=HIMS_ENVIRONMENT,
    deployment_id=HIMS_DEPLOYMENT_ID,
    database_host=DATABASES["default"].get("HOST", ""),
    database_environment=HIMS_DATABASE_ENVIRONMENT,
    debug=DEBUG,
)
