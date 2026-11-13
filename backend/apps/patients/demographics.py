"""Names, ages and phone numbers as the front desk types them (P0 part 01, section 1 "Rules").

* Names: any script (D26), trimmed, no digits; one name is enough.
* Age instead of a date of birth: years (or months / days for babies) give an estimated date,
  1 July of the birth year (D2), marked "estimated".
* Phones: stored in international format (E.164), using the hospital's country when the person
  types a local number. Phones are often shared in a family, so a phone never identifies a
  patient on its own (part 05).
"""

import re
import unicodedata
from datetime import date, timedelta

MAX_AGE_YEARS = 130
COUNTRY_CODES = {"IN": "91", "US": "1"}
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


class InvalidValue(ValueError):
    pass


def clean_name(value: str, *, label: str, required: bool = False) -> str:
    value = " ".join(unicodedata.normalize("NFC", value or "").split())
    if required and not value:
        raise InvalidValue(f"{label} is required.")
    if any(char.isdigit() for char in value):
        raise InvalidValue(f"{label} cannot contain numbers.")
    return value


def search_name(*names: str) -> str:
    """Lower-case, single-spaced, accents kept: what patient search compares (HIMS-PAT-002)."""
    words = " ".join(name for name in names if name).casefold().split()
    return " ".join(dict.fromkeys(words))[:500]


def years_between(born: date, today: date) -> int:
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def check_date_of_birth(born: date, today: date) -> None:
    if born > today:
        raise InvalidValue("The date of birth cannot be in the future.")
    if years_between(born, today) > MAX_AGE_YEARS:
        raise InvalidValue(f"The date of birth cannot be more than {MAX_AGE_YEARS} years ago.")


def _months_back(today: date, months: int) -> date:
    total = today.year * 12 + (today.month - 1) - months
    year, month = divmod(total, 12)
    day = min(today.day, 28)  # every month has a 28th
    return date(year, month + 1, day)


def estimated_date_of_birth(today: date, *, years=None, months=None, days=None) -> date:
    """The approximate birth date for an age. Years: 1 July of the birth year (D2)."""
    if years:
        if not 0 < years <= MAX_AGE_YEARS:
            raise InvalidValue(f"Age must be between 1 and {MAX_AGE_YEARS} years.")
        born = date(today.year - years, 7, 1)
        if years_between(born, today) < years:  # 1 July has not come yet this year
            born = date(today.year - years - 1, 7, 1)
        return born
    if months:
        if not 0 < months < 24:
            raise InvalidValue("Give the age in months up to 23 months, then in years.")
        return _months_back(today, months)
    if days is not None:
        if not 0 <= days <= 60:
            raise InvalidValue("Give the age in days up to 60 days, then in months.")
        return today - timedelta(days=days)
    raise InvalidValue("Give the date of birth or the age.")


def age_text(born: date, today: date) -> str:
    """Short age for lists: '34 y', '5 m', '12 d'."""
    years = years_between(born, today)
    if years >= 2:
        return f"{years} y"
    months = (today.year - born.year) * 12 + today.month - born.month - (today.day < born.day)
    if months >= 1:
        return f"{months} m"
    return f"{(today - born).days} d"


def normalise_phone(value: str, *, country: str, mobile: bool = False) -> str:
    """'+91 98765 43210', '098765 43210' or '9876543210' -> '+919876543210' (India);
    '(312) 555-0142' -> '+13125550142' (US). ``mobile``: an Indian number must be a mobile."""
    raw = (value or "").strip()
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+"):
        number = f"+{digits}"
    elif raw.startswith("00"):
        number = f"+{digits[2:]}"
    elif country == "IN" and len(digits) == 11 and digits.startswith("0"):
        number = f"+91{digits[1:]}"
    elif country == "US" and len(digits) == 11 and digits.startswith("1"):
        number = f"+{digits}"
    elif len(digits) == 10 and country in COUNTRY_CODES:
        number = f"+{COUNTRY_CODES[country]}{digits}"
    else:
        raise InvalidValue("Enter the phone number with its country code, e.g. +91 98765 43210.")
    if not _E164.match(number):
        raise InvalidValue("This phone number is not valid.")
    if number.startswith("+91") and len(number) != 13:
        raise InvalidValue("An Indian phone number has 10 digits (with the area code).")
    if number.startswith("+91") and mobile and number[3] not in "6789":
        raise InvalidValue("An Indian mobile number starts with 6, 7, 8 or 9.")
    if number.startswith("+1") and len(number) != 12:
        raise InvalidValue("A US phone number has 10 digits (area code and number).")
    return number


def phone_last4(number: str) -> str:
    return f"…{number[-4:]}" if number else ""
