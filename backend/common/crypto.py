"""Application-level encryption for secrets that must be readable again, such as two-factor
authenticator keys (spec 13.3: encryption at rest, managed keys and rotation).

Keys come from ``HIMS_FIELD_ENCRYPTION_KEYS``: a list of Fernet keys, newest first. New values
are encrypted with the first key; any listed key can decrypt, so keys can be rotated by adding a
new key at the front and re-encrypting later. In managed environments the keys come from the
secret manager (one set per environment and per customer) and production refuses to start
without them. On developer machines and in tests a key derived from DJANGO_SECRET_KEY is used
when none is configured.

Generate a key:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

LOCAL_ENVIRONMENTS = {"local", "test"}


class DecryptionError(Exception):
    pass


def _derived_local_key() -> bytes:
    digest = hashlib.sha256(f"hims-field-encryption:{settings.SECRET_KEY}".encode()).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache(maxsize=4)
def _fernet(keys: tuple[str, ...], environment: str) -> MultiFernet:
    if keys:
        return MultiFernet([Fernet(key.encode()) for key in keys])
    if environment in LOCAL_ENVIRONMENTS:
        return MultiFernet([Fernet(_derived_local_key())])
    raise ImproperlyConfigured("HIMS_FIELD_ENCRYPTION_KEYS must be set in managed environments.")


def _cipher() -> MultiFernet:
    return _fernet(tuple(settings.HIMS_FIELD_ENCRYPTION_KEYS), settings.HIMS_ENVIRONMENT)


def encrypt(plaintext: str) -> str:
    return _cipher().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _cipher().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError(
            "Stored secret could not be decrypted with the configured keys."
        ) from exc


def key_count() -> int:
    return len(settings.HIMS_FIELD_ENCRYPTION_KEYS) or 1


def is_on_newest_key(token: str) -> bool:
    """True when the newest key (the first) can read the value, so older keys are not needed."""
    configured = settings.HIMS_FIELD_ENCRYPTION_KEYS
    newest = Fernet(configured[0].encode()) if configured else Fernet(_derived_local_key())
    try:
        newest.decrypt(token.encode())
    except InvalidToken:
        return False
    return True


def rotate(token: str) -> str:
    """The same value, encrypted again with the newest key (HIMS-SEC-011)."""
    try:
        return _cipher().rotate(token.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError(
            "Stored secret could not be decrypted with the configured keys."
        ) from exc
