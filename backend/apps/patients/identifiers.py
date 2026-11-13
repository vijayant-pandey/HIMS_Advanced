"""ID numbers: which kinds each country uses, how they are checked, masked and fingerprinted.

Country rules: docs/p0/phase-2-patients/05-country-privacy-terminology.md and decisions D6-D8
(PO, 2026-10-30): Aadhaar and SSN may be typed in now, marked "not verified", stored encrypted
and shown masked; ABHA is recorded as typed until the ABDM integration (Phase 6).

The full number is encrypted with the field-encryption keys (common.crypto). To find a number and
refuse it on a second patient, a keyed fingerprint (HMAC-SHA256) of the normalised number is
stored; the key is random per hospital and kept encrypted (``IdentifierHashKey``).
"""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

from django.db import transaction

from common import crypto

from .models import IdentifierHashKey, PatientIdentifier

Kind = PatientIdentifier.Kind


@dataclass(frozen=True)
class KindRule:
    countries: frozenset[str]
    pattern: re.Pattern
    example: str
    needs_issuer: bool = False


_ALNUM = re.compile(r"^[A-Z0-9]{5,20}$")
RULES: dict[str, KindRule] = {
    Kind.ABHA_NUMBER: KindRule(frozenset({"IN"}), re.compile(r"^\d{14}$"), "91-1234-5678-9012"),
    Kind.ABHA_ADDRESS: KindRule(
        frozenset({"IN"}), re.compile(r"^[a-z0-9._]{4,32}@[a-z]{2,10}$"), "name.surname@abdm"
    ),
    Kind.AADHAAR: KindRule(frozenset({"IN"}), re.compile(r"^[2-9]\d{11}$"), "1234 5678 9012"),
    Kind.VOTER_ID: KindRule(frozenset({"IN"}), _ALNUM, "ABC1234567"),
    Kind.SSN: KindRule(frozenset({"US"}), re.compile(r"^\d{9}$"), "123-45-6789"),
    Kind.PASSPORT: KindRule(frozenset({"IN", "US"}), re.compile(r"^[A-Z0-9]{6,20}$"), "K1234567"),
    Kind.DRIVING_LICENCE: KindRule(frozenset({"IN", "US"}), _ALNUM, "DL0420110012345"),
    Kind.PREVIOUS_MRN: KindRule(
        frozenset({"IN", "US"}),
        re.compile(r"^[A-Z0-9][A-Z0-9/-]{0,39}$"),
        "OLD-000123",
        needs_issuer=True,
    ),
}


class InvalidIdentifier(ValueError):
    pass


def kinds_for(country: str) -> list[str]:
    return [kind for kind, rule in RULES.items() if country in rule.countries]


# Verhoeff check digit, used by Aadhaar: catches every single-digit typo and swapped neighbours.
_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def verhoeff_ok(digits: str) -> bool:
    check = 0
    for position, digit in enumerate(reversed(digits)):
        check = _D[check][_P[position % 8][int(digit)]]
    return check == 0


def _ssn_ok(digits: str) -> bool:
    area, group, serial = digits[:3], digits[3:5], digits[5:]
    return area not in ("000", "666") and area[0] != "9" and group != "00" and serial != "0000"


def normalise(kind: str, value: str) -> str:
    """The number as stored and compared: no spaces or dashes, capitals (ABHA address: lower)."""
    value = (value or "").strip()
    if kind == Kind.ABHA_ADDRESS:
        return value.lower()
    if kind in (Kind.AADHAAR, Kind.ABHA_NUMBER, Kind.SSN):
        return re.sub(r"[\s-]", "", value)
    if kind == Kind.PREVIOUS_MRN:
        return re.sub(r"\s", "", value).upper()
    return re.sub(r"[\s-]", "", value).upper()


def check(kind: str, value: str, *, country: str) -> str:
    """The normalised number, or InvalidIdentifier with a message for the front desk."""
    rule = RULES.get(kind)
    if rule is None:
        raise InvalidIdentifier("Unknown kind of ID number.")
    if country not in rule.countries:
        raise InvalidIdentifier(f"{Kind(kind).label} is not used in this hospital's country.")
    number = normalise(kind, value)
    if not rule.pattern.match(number):
        raise InvalidIdentifier(
            f"This does not look like a valid {Kind(kind).label} (e.g. {rule.example})."
        )
    if kind == Kind.AADHAAR and not verhoeff_ok(number):
        raise InvalidIdentifier("This Aadhaar number has a typing mistake (its check digit fails).")
    if kind == Kind.SSN and not _ssn_ok(number):
        raise InvalidIdentifier("This is not a valid Social Security number.")
    return number


def mask(kind: str, number: str) -> str:
    """What screens show: never more than the last 4 characters (previous MRNs in full)."""
    if kind == Kind.AADHAAR:
        return f"XXXX XXXX {number[-4:]}"
    if kind == Kind.SSN:
        return f"XXX-XX-{number[-4:]}"
    if kind == Kind.ABHA_NUMBER:
        return f"XX-XXXX-XXXX-{number[-4:]}"
    if kind == Kind.ABHA_ADDRESS:
        local, _, domain = number.partition("@")
        return f"{local[:2]}{'*' * max(len(local) - 2, 2)}@{domain}"
    if kind == Kind.PREVIOUS_MRN:
        return number
    return f"{'X' * max(len(number) - 4, 2)}{number[-4:]}"


@transaction.atomic
def _hash_key() -> bytes:
    row = IdentifierHashKey.objects.select_for_update().order_by("created_at").first()
    if row is None:
        row = IdentifierHashKey.objects.create(key_encrypted=crypto.encrypt(secrets.token_hex(32)))
    return crypto.decrypt(row.key_encrypted).encode()


def fingerprint(kind: str, number: str, *, issuer: str = "") -> str:
    """Keyed fingerprint of a normalised number (previous MRNs include the hospital they are from,
    since two hospitals may use the same number)."""
    scope = issuer.strip().lower() if kind == Kind.PREVIOUS_MRN else ""
    message = f"{kind}|{scope}|{number}".encode()
    return hmac.new(_hash_key(), message, hashlib.sha256).hexdigest()
