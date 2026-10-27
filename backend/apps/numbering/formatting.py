"""Pure formatting rules for business numbers (HIMS-ORG-003). No database access.

A number is built from up to four parts joined by the scheme's separator:

    [prefix] [facility code] [period] [zero-padded sequence]
    MRN-00000123        INV/26-27/000042        ENC-BLR-2026-0000007

The *period key* identifies the counter (it is what makes the sequence restart). It is always
stored in full (``2026``, ``2026-27``, ``202610``) so that switching the display between full and
short years never restarts or duplicates a sequence.
"""

from dataclasses import dataclass
from datetime import date

NONE = "none"
CALENDAR_YEAR = "calendar_year"
FINANCIAL_YEAR = "financial_year"
MONTH = "month"


@dataclass(frozen=True)
class Format:
    prefix: str
    separator: str
    include_facility_code: bool
    period: str
    year_format: str  # "full" or "short"
    financial_year_start_month: int
    padding: int


def financial_year_start(on: date, start_month: int) -> int:
    return on.year if on.month >= start_month else on.year - 1


def period_key(fmt: Format, on: date) -> str:
    if fmt.period == CALENDAR_YEAR:
        return f"{on.year}"
    if fmt.period == MONTH:
        return f"{on.year}{on.month:02d}"
    if fmt.period == FINANCIAL_YEAR:
        start = financial_year_start(on, fmt.financial_year_start_month)
        if fmt.financial_year_start_month == 1:
            return f"{start}"  # a January-start financial year is the calendar year
        return f"{start}-{(start + 1) % 100:02d}"
    return ""


def period_label(fmt: Format, key: str) -> str:
    """The period as printed in the number, e.g. ``2026-27`` or (short) ``26-27``."""
    if not key or fmt.year_format != "short":
        return key
    if fmt.period == MONTH:
        return key[2:]  # 202610 -> 2610
    if "-" in key:
        start, end = key.split("-")
        return f"{start[2:]}-{end}"  # 2026-27 -> 26-27
    return key[2:]  # 2026 -> 26


def format_number(fmt: Format, *, sequence: int, key: str, facility_code: str = "") -> str:
    parts = []
    if fmt.prefix:
        parts.append(fmt.prefix)
    if fmt.include_facility_code and facility_code:
        parts.append(facility_code.upper())
    if fmt.period != NONE:
        parts.append(period_label(fmt, key))
    parts.append(str(sequence).zfill(fmt.padding))
    return fmt.separator.join(parts)
