"""Wrong-password limit per account, on top of the limit per address (spec 13.1; HIMS-SEC-011
finding F-02).

The sign-in rate limit counts per client address, so guessing one person's password from many
addresses was never slowed down. Here failed sign-ins are also counted per email address: after
``HIMS_SIGN_IN_MAX_FAILURES`` failures within ``HIMS_SIGN_IN_PAUSE_SECONDS``, sign-in with that
email is paused for that long, in the app and the admin console alike.

The count is kept for every email typed, whether or not an account uses it, and the pause answer
is the same either way, so it reveals nothing about which accounts exist. A correct password
clears the count. The cache is shared by all server processes when hosted (Redis).
"""

import hashlib

from django.conf import settings
from django.core.cache import cache

from common.exceptions import DomainError


class SignInPaused(DomainError):
    status_code = 429
    code = "SIGN_IN_PAUSED"
    title = "Sign-in paused"


def _key(email: str) -> str:
    digest = hashlib.sha256((email or "").strip().lower().encode()).hexdigest()
    return f"sign-in-failures:{digest}"


def failures(email: str) -> int:
    return cache.get(_key(email), 0)


def check(email: str) -> None:
    """Raise SignInPaused when this email has had too many wrong passwords lately."""
    if failures(email) >= settings.HIMS_SIGN_IN_MAX_FAILURES:
        minutes = settings.HIMS_SIGN_IN_PAUSE_SECONDS // 60
        raise SignInPaused(
            f"Too many wrong passwords for this email. Sign-in is paused for {minutes} minutes; "
            "if you forgot your password, use Forgot password."
        )


def record_failure(email: str) -> None:
    key = _key(email)
    cache.add(key, 0, settings.HIMS_SIGN_IN_PAUSE_SECONDS)
    try:
        cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, settings.HIMS_SIGN_IN_PAUSE_SECONDS)


def clear(email: str) -> None:
    cache.delete(_key(email))
