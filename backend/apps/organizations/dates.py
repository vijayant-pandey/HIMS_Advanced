"""Calendar dates as the hospital sees them (HIMS-STAFF-011).

Instants are stored in UTC (settings.TIME_ZONE). A date people act on, such as a licence expiry,
the last day of a posting or a review's finish-by date, is a date where the hospital is, so
"today" is taken in the hospital's time zone. In India UTC is still on yesterday until 5:30 am,
and in the US it is already tomorrow from late afternoon or evening.

Things that belong to one facility use that facility's time zone; hospital-wide things (licences,
access reviews, times in emails) use the hospital's default time zone (Hospital settings).

Within one request the hospital's time zone is read once (``request_memo``): a list of 50
patients with their ages, or a console list of times, used to read it once per row
(HIMS-DATA-003). Changing it in Hospital settings clears it (``forget_hospital_timezone``).
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from common.request_context import request_memo

_MEMO_KEY = "hospital_timezone"


def _hospital_zone_name() -> str | None:
    from .models import Organization

    memo = request_memo()
    if memo is not None and _MEMO_KEY in memo:
        return memo[_MEMO_KEY]
    zone = (
        Organization.objects.filter(deployment_id=settings.HIMS_DEPLOYMENT_ID)
        .values_list("default_timezone", flat=True)
        .first()
    )
    if memo is not None:
        memo[_MEMO_KEY] = zone
    return zone


def forget_hospital_timezone() -> None:
    """After the hospital's time zone changes, the rest of the request reads the new one."""
    memo = request_memo()
    if memo is not None:
        memo.pop(_MEMO_KEY, None)


def hospital_timezone(facility=None) -> ZoneInfo:
    if facility is not None and facility.timezone:
        return ZoneInfo(facility.timezone)
    return ZoneInfo(_hospital_zone_name() or settings.TIME_ZONE)  # not provisioned yet: UTC


def hospital_time(instant: datetime, facility=None) -> datetime:
    """An instant on the hospital's clock, for emails (format with %Z to name the zone)."""
    return instant.astimezone(hospital_timezone(facility))


def hospital_date(instant: datetime, facility=None) -> date:
    """The calendar date of an instant where the hospital (or facility) is."""
    return hospital_time(instant, facility).date()


def hospital_today(facility=None) -> date:
    return hospital_date(timezone.now(), facility)
