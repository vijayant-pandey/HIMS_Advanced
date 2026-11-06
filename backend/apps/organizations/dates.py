"""Calendar dates as the hospital sees them (HIMS-STAFF-011).

Instants are stored in UTC (settings.TIME_ZONE). A date people act on, such as a licence expiry,
the last day of a posting or a review's finish-by date, is a date where the hospital is, so
"today" is taken in the hospital's time zone. In India UTC is still on yesterday until 5:30 am,
and in the US it is already tomorrow from late afternoon or evening.

Things that belong to one facility use that facility's time zone; hospital-wide things (licences,
access reviews, times in emails) use the hospital's default time zone (Hospital settings).
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


def hospital_timezone(facility=None) -> ZoneInfo:
    if facility is not None and facility.timezone:
        return ZoneInfo(facility.timezone)
    from .models import Organization

    zone = (
        Organization.objects.filter(deployment_id=settings.HIMS_DEPLOYMENT_ID)
        .values_list("default_timezone", flat=True)
        .first()
    )
    return ZoneInfo(zone or settings.TIME_ZONE)  # not provisioned yet: UTC


def hospital_time(instant: datetime, facility=None) -> datetime:
    """An instant on the hospital's clock, for emails (format with %Z to name the zone)."""
    return instant.astimezone(hospital_timezone(facility))


def hospital_date(instant: datetime, facility=None) -> date:
    """The calendar date of an instant where the hospital (or facility) is."""
    return hospital_time(instant, facility).date()


def hospital_today(facility=None) -> date:
    return hospital_date(timezone.now(), facility)
