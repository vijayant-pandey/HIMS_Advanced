"""Secrets never reach a log (HIMS-SEC-019; spec 13.3, 13.4, 13.5 "an integration logs a secret
or sensitive patient data during an exception", 27.2).

Every log line passes through :func:`scrub_value` (see ``common.logging.JsonFormatter``), and
error texts kept in the database (a failed email's "last error") pass through :func:`scrub`.
What is hidden, whatever code wrote the line:

* the values of this deployment's own secrets (Django secret key, database and email passwords,
  encryption and audit-chain keys, tracing headers), wherever they appear;
* passwords in addresses (``postgres://user:secret@host``) and ``Bearer``/``Basic`` credentials;
* every value in a query string or link fragment (``?search=…``, ``#token=…``): sign-in links,
  signed download links and search words such as a patient's name;
* values written as ``password=…``, ``"token": "…"``, ``api_key: …`` and similar, and personal
  details written the same way (``display_name=…``, ``phone: …``, ``text='…'``, ``patient…``);
* email addresses and phone numbers in international form (``+91…``);
* the row values PostgreSQL puts in error messages (``Key (email)=(…)``, ``Failing row
  contains (…)``), which would otherwise copy a person's details into the log;
* extra fields whose name says they hold a secret or a payload (``password``, ``token``,
  ``recovery_codes``, ``args``, ``body``…), and a request is written as method and path only.

This is the safety net, not the rule: code still logs identifiers and outcomes, never contents.
"""

import os
import re
from functools import lru_cache

from django.conf import settings
from django.core.signals import setting_changed

HIDDEN = "[hidden]"
_MIN_SECRET_LENGTH = 8  # shorter values would hide ordinary words

# Settings and environment variables whose value is a secret, and look-alikes that are not.
_SECRET_NAME = re.compile(
    r"SECRET|PASSWORD|PASSWD|TOKEN|PRIVATE_KEY|ACCESS_KEY|ENCRYPTION_KEYS|CHAIN_KEYS|OTLP\w*HEADERS"
)
_NOT_SECRET_NAME = re.compile(r"HASHERS|VALIDATORS|TTL|TIMEOUT|MAX_|THROTTLE|_URL$")

# Names (of log fields, or written as "name=value" in text) whose value is a secret or a
# personal detail. Names ending in _id, _ids or _count are identifiers and counts: kept.
_CONFIDENTIAL_WORDS = (
    r"password|passwd|passphrase|secret|token|otp|api[_-]?key|private[_-]?key|access[_-]?key"
    r"|authorization|cookie|sessionid|session[_-]?key|csrf|recovery[_-]?codes?|mfa[_-]?code|dsn"
    r"|database[_-]?url"
)
_PERSONAL_WORDS = (
    r"display[_-]?name|given[_-]?name|family[_-]?name|full[_-]?name|patient|phone|mobile|email"
    r"|address|date[_-]?of[_-]?birth|dob|text|note|diagnosis"
)
_SENSITIVE_KEY = re.compile(f"(?i){_CONFIDENTIAL_WORDS}|{_PERSONAL_WORDS}")
_IDENTIFIER_KEY = re.compile(r"(?i)_(ids?|count)$")
_PAYLOAD_KEYS = frozenset({"args", "kwargs", "body", "payload", "request_body"})

_URL_PASSWORD = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://[^\s:/@]*:)\S*@")
_AUTH_SCHEME = re.compile(r"\b(Bearer|Basic|Token)\s+[A-Za-z0-9._~+/=\-]{6,}")
_QUERY_VALUE = re.compile(r"([?&#][A-Za-z0-9_.\-\[\]%]+=)(?!\[hidden\])[^&#\s\"'<>]*")
_KEYED_VALUE = re.compile(
    rf"(?i)\b([\w-]*(?:{_CONFIDENTIAL_WORDS}|{_PERSONAL_WORDS}|body)[\w-]*)"
    r"([\"']?\s*[:=]\s*)"
    r"(?!\[hidden\]|[:=(])(\"[^\"]*\"|'[^']*'|[^\s,;&}\]\"']+)"
)
# "Key (lower(email::text))=(asha@…) already exists", "… conflicts with existing key (…)=(…)."
_PG_KEY_VALUES = re.compile(
    r"(?i)(key \((?:[^()]|\([^()]*\))*\)=\()(.*?)"
    r"(\)(?=\.| already exists| is not present| conflicts with| is still referenced))"
)
_EMAIL = re.compile(r"[\w.+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")
_PHONE = re.compile(r"(?<![\w+])\+\d[\d \-]{6,16}\d\b")
_PG_FAILING_ROW = re.compile(r"(Failing row contains \().*?(\)\.?$)", re.MULTILINE)


def _secret_values_of(name: str, value) -> list[str]:
    if not _SECRET_NAME.search(name) or _NOT_SECRET_NAME.search(name):
        return []
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)):
        return []
    found = []
    for item in values:
        if isinstance(item, str):
            found.append(item)
            if name.endswith("CHAIN_KEYS"):  # "key-id:secret"
                found.append(item.partition(":")[2])
    return found


@lru_cache(maxsize=1)
def known_secrets() -> tuple[str, ...]:
    """This deployment's own secret values, longest first."""
    found = []
    for name in dir(settings):
        if name.isupper():
            found += _secret_values_of(name, getattr(settings, name, None))
    for name, value in os.environ.items():
        found += _secret_values_of(name.upper(), value)
    for database in getattr(settings, "DATABASES", {}).values():
        found.append(str(database.get("PASSWORD") or ""))
    unique = {value for value in found if len(value) >= _MIN_SECRET_LENGTH}
    return tuple(sorted(unique, key=len, reverse=True))


def _forget_secrets(**kwargs) -> None:
    known_secrets.cache_clear()


setting_changed.connect(_forget_secrets, dispatch_uid="hims.log_safety.forget_secrets")


def _keyed(match: re.Match) -> str:
    if _IDENTIFIER_KEY.search(match.group(1)):
        return match.group(0)
    value = match.group(3)
    quote = value[0] if value[:1] in "\"'" else ""
    return f"{match.group(1)}{match.group(2)}{quote}{HIDDEN}{quote}"


def scrub(text: str, extra_secrets=()) -> str:
    """``text`` with every secret and personal value this module knows about hidden."""
    if not text:
        return text
    for secret in (*known_secrets(), *extra_secrets):
        if secret:
            text = text.replace(secret, HIDDEN)
    text = _PG_KEY_VALUES.sub(rf"\1{HIDDEN}\3", text)
    text = _PG_FAILING_ROW.sub(rf"\1{HIDDEN}\2", text)
    text = _URL_PASSWORD.sub(rf"\1{HIDDEN}@", text)
    text = _AUTH_SCHEME.sub(rf"\1 {HIDDEN}", text)
    text = _QUERY_VALUE.sub(rf"\1{HIDDEN}", text)
    text = _KEYED_VALUE.sub(_keyed, text)
    text = _EMAIL.sub(HIDDEN, text)
    return _PHONE.sub(HIDDEN, text)


def is_sensitive_key(key) -> bool:
    name = str(key).lower()
    if name in _PAYLOAD_KEYS:
        return True
    return bool(_SENSITIVE_KEY.search(name)) and not _IDENTIFIER_KEY.search(name)


def _is_request(value) -> bool:
    return all(hasattr(value, attribute) for attribute in ("method", "path", "META"))


def scrub_value(key, value):
    """A log field's value made safe to write (nested dictionaries and lists included)."""
    if key is not None and is_sensitive_key(key):
        return HIDDEN
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if _is_request(value):  # Django/DRF request: never the query string, headers or body
        return f"{value.method} {value.path}"
    if isinstance(value, dict):
        return {str(k): scrub_value(k, v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [scrub_value(None, item) for item in value]
    return scrub(str(value))


def hidden_parts(readable: str, real: str) -> list[str] | None:
    """The pieces of ``real`` that its ``readable`` copy shows as ``[hidden]`` (for example the
    sign-in link in an email), or None when the two do not line up."""
    if HIDDEN not in readable:
        return []
    pattern = "(.*?)".join(re.escape(piece) for piece in readable.split(HIDDEN))
    match = re.fullmatch(pattern, real, flags=re.DOTALL)
    if match is None:
        return None
    return [part for part in match.groups() if part]
