"""Signed one-time link tokens (invitations, password resets).

A token is a signature over the ID of a database row that holds the link's state (expiry,
used/revoked). The secret itself is never stored, so a database leak does not expose working
links. Each purpose uses its own salt, so a token for one purpose cannot be replayed as another.
Links carry the token in the URL fragment (``#token=...``), which browsers never send to servers
(spec 29.1).
"""

from django.conf import settings
from django.core import signing


def make_link_token(row_id, *, salt: str) -> str:
    return signing.dumps(str(row_id), salt=salt)


def read_link_token(token: str, *, salt: str) -> str | None:
    """Return the row ID the token was issued for, or None if it is not genuine."""
    try:
        return signing.loads(token, salt=salt)
    except (signing.BadSignature, TypeError, ValueError):
        return None


def app_link(path: str, token: str) -> str:
    return f"{settings.HIMS_APP_BASE_URL.rstrip('/')}/{path.lstrip('/')}#token={token}"
