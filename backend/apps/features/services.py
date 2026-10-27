"""Read and change feature settings (HIMS-ORG-004).

Code asks ``is_enabled(F.SOMETHING, facility_id=..., request=request)``. Settings are read from
the database in one small query and remembered for the rest of that request, so a change made in
the app or the admin console takes effect on the very next request in every server process.
"""

from django.db import transaction
from django.db.models import Q

from apps.audit.services import AuditAction, record_audit_event
from common.concurrency import bump_version
from common.exceptions import ConflictError, StaleResourceError

from . import catalog
from .catalog import BY_KEY, FACILITY, Feature
from .models import FeatureFlag

_REQUEST_CACHE = "_hims_feature_settings"


class FeatureDisabled(ConflictError):
    code = "FEATURE_DISABLED"
    title = "Feature turned off"


class _Settings:
    """Every stored setting plus the hospital's country: one snapshot per request."""

    def __init__(self):
        from apps.organizations.models import Organization

        self.country = Organization.objects.values_list("country", flat=True).first() or ""
        self.values: dict[tuple[str, object], bool] = {
            (key, facility_id): enabled
            for key, facility_id, enabled in FeatureFlag.objects.filter(
                enabled__isnull=False
            ).values_list("key", "facility_id", "enabled")
        }

    def default(self, feature: Feature) -> bool:
        return feature.country_defaults.get(self.country, feature.default)

    def offered(self, feature: Feature) -> bool:
        return feature.available and (not feature.countries or self.country in feature.countries)

    def hospital(self, feature: Feature) -> bool:
        if not self.offered(feature):
            return False
        value = self.values.get((feature.key, None))
        return self.default(feature) if value is None else value

    def at(self, feature: Feature, facility_id) -> bool:
        if not self.offered(feature):
            return False
        if facility_id is not None and feature.scope == FACILITY:
            value = self.values.get((feature.key, facility_id))
            if value is not None:
                return value
        return self.hospital(feature)


def current_settings(request=None) -> _Settings:
    if request is None:
        return _Settings()
    cached = getattr(request, _REQUEST_CACHE, None)
    if cached is None:
        cached = _Settings()
        setattr(request, _REQUEST_CACHE, cached)
    return cached


def is_enabled(key: str, *, facility_id=None, request=None) -> bool:
    return current_settings(request).at(BY_KEY[key], facility_id)


def require_enabled(key: str, *, facility_id=None, request=None) -> None:
    if not is_enabled(key, facility_id=facility_id, request=request):
        feature = BY_KEY[key]
        where = " for this facility" if facility_id and feature.scope == FACILITY else ""
        raise FeatureDisabled(
            f"{feature.name} is turned off{where}. An administrator can turn it on under Features."
        )


def disabled_facility_ids(key: str, *, request=None) -> set:
    """Facilities where a per-facility feature is off (to hide their rows from lists)."""
    from apps.facilities.models import Facility

    settings_ = current_settings(request)
    feature = BY_KEY[key]
    return {
        pk for pk in Facility.objects.values_list("pk", flat=True) if not settings_.at(feature, pk)
    }


def states(*, facility=None, request=None) -> list[dict]:
    """Every feature with its default, settings and current value, for the Features page."""
    settings_ = current_settings(request)
    scope = Q(facility__isnull=True)
    if facility is not None:
        scope |= Q(facility=facility)
    rows = {
        (row.key, row.facility_id): row
        for row in FeatureFlag.objects.filter(scope).select_related("updated_by")
    }
    result = []
    for feature in catalog.FEATURES:
        if facility is not None and feature.scope != FACILITY:
            continue
        hospital_row = rows.get((feature.key, None))
        facility_row = rows.get((feature.key, facility.pk)) if facility else None
        result.append(
            {
                "feature": feature,
                "offered_in_country": not feature.countries
                or settings_.country in feature.countries,
                "default": settings_.default(feature),
                "hospital_row": hospital_row,
                "facility_row": facility_row,
                "enabled": settings_.at(feature, facility.pk if facility else None),
            }
        )
    return result


@transaction.atomic
def set_feature(
    *, actor, key: str, facility=None, enabled: bool | None, reason: str, version: int, request=None
) -> FeatureFlag:
    """Turn a feature on/off (or back to the default) for the hospital or one facility.

    ``version`` is the setting's current version, or 0 when it has never been set.
    """
    feature = BY_KEY.get(key)
    if feature is None:
        raise ConflictError("Unknown feature.", code="UNKNOWN_FEATURE")
    before_value = is_enabled(key, facility_id=facility.pk if facility else None)
    row = (
        FeatureFlag.objects.select_for_update()
        .filter(key=key, facility=facility)
        .order_by()  # default ordering joins facilities, which cannot be locked
        .first()
    )
    if row is None:
        if version != 0:
            raise StaleResourceError("This setting changed since you loaded it. Reload and retry.")
        row = FeatureFlag(key=key, facility=facility)
        previous = None
    else:
        if row.version != version:
            raise StaleResourceError("This setting changed since you loaded it. Reload and retry.")
        previous = row.enabled
        bump_version(row)
    row.enabled = enabled
    row.reason = (reason or "").strip()
    row.updated_by = actor
    row.full_clean()
    row.save()
    after_value = is_enabled(key, facility_id=facility.pk if facility else None)
    record_audit_event(
        action=AuditAction.FEATURE_FLAG_CHANGED,
        resource_type="feature_flag",
        resource_id=row.pk,
        facility_id=facility.pk if facility else None,
        actor=actor,
        request=request,
        reason=row.reason,
        changes={
            "before": {"setting": setting_label(previous), "effective": before_value},
            "after": {"setting": setting_label(enabled), "effective": after_value},
        },
        metadata={"feature": key},
    )
    if request is not None and hasattr(request, _REQUEST_CACHE):
        delattr(request, _REQUEST_CACHE)
    return row


def setting_label(value: bool | None) -> str:
    return "default" if value is None else ("on" if value else "off")


def ensure_hospital_rows(organization) -> list[str]:
    """Give every catalog feature a hospital-wide row set to "use the default", so the admin
    console lists them all. Never changes an existing setting. Safe to run repeatedly."""
    existing = set(FeatureFlag.objects.filter(facility__isnull=True).values_list("key", flat=True))
    missing = [feature.key for feature in catalog.FEATURES if feature.key not in existing]
    FeatureFlag.objects.bulk_create(
        [
            FeatureFlag(
                organization=organization,
                key=key,
                facility=None,
                enabled=None,
                reason="Added with the default setting",
            )
            for key in missing
        ]
    )
    if missing:
        record_audit_event(
            action=AuditAction.FEATURE_CATALOG_SYNCED,
            resource_type="feature_flag",
            organization_id=organization.pk,
            metadata={"added": missing, "setting": "default"},
        )
    return missing
