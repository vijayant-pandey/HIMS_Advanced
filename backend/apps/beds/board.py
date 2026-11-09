"""The bed board: every ward's beds and their status on one screen (spec 4.10, 15.1; HIMS-FAC-008).

No patients yet: admissions fill beds in Phase 3. Who sees what follows ``locations.view``:
a hospital-wide or facility grant shows every ward of the facility; a department grant shows
the wards of that department (ward staff are usually granted at department level). Only
active wards, rooms and beds are shown; facilities where the hospital switched Locations off
(HIMS-ORG-004) are left out. The screen asks again every 30 seconds.
"""

from collections import Counter

from django.db.models import Prefetch
from django.utils import timezone

from apps.access_control.catalog import P
from apps.access_control.selectors import get_permission_scope
from apps.facilities.models import Facility, Ward
from apps.features.catalog import F
from apps.features.services import disabled_facility_ids

from .models import Bed, BedStatusChange

HISTORY_LIMIT = 20


def visible_facilities(user, request=None) -> list[Facility]:
    scope = get_permission_scope(user, P.LOCATIONS_VIEW)
    facilities = Facility.objects.filter(status=Facility.Status.ACTIVE).exclude(
        pk__in=disabled_facility_ids(F.LOCATIONS, request=request)
    )
    ids = scope.visible_facility_ids()
    if ids is not None:
        facilities = facilities.filter(pk__in=ids)
    return list(facilities.order_by("name"))


def _visible_wards(scope, facility_id):
    wards = Ward.objects.filter(facility_id=facility_id, is_active=True)
    if scope.org_wide or facility_id in scope.facility_ids:
        return wards
    departments = {d for f, d in scope.department_ids if f == facility_id}
    return wards.filter(department_id__in=departments)


def build_board(user, *, facility_id=None, request=None) -> dict:
    facilities = visible_facilities(user, request=request)
    chosen = next((f for f in facilities if str(f.pk) == str(facility_id)), None)
    if chosen is None and facilities and facility_id is None:
        chosen = facilities[0]
    board = {
        "generated_at": timezone.now(),
        "facilities": [{"id": f.pk, "code": f.code, "name": f.name} for f in facilities],
        "facility": chosen.pk if chosen else None,
        "bed_counts": {},
        "available_by_type": {},
        "wards": [],
    }
    if chosen is None:
        return board

    view_scope = get_permission_scope(user, P.LOCATIONS_VIEW)
    change_scope = get_permission_scope(user, P.BEDS_STATUS_MANAGE)
    beds = (
        Bed.objects.filter(is_active=True, room__is_active=True)
        .select_related("room")
        .order_by("room__code", "code")
    )
    wards = (
        _visible_wards(view_scope, chosen.pk)
        .filter(floor__is_active=True, floor__building__is_active=True)
        .select_related("floor__building", "department")
        .prefetch_related(Prefetch("beds", queryset=beds))
        .order_by("floor__building__code", "floor__level", "code")
    )
    totals, available = Counter(), Counter()
    for ward in wards:
        ward_beds = [
            {
                "id": bed.pk,
                "code": bed.code,
                "bed_type": bed.bed_type,
                "status": bed.status,
                "status_reason": bed.status_reason,
                "status_changed_at": bed.status_changed_at,
                "version": bed.version,
                "room_code": bed.room.code,
                "room_name": bed.room.name,
                "is_isolation_capable": bed.room.is_isolation_capable,
            }
            for bed in ward.beds.all()
        ]
        counts = Counter(bed["status"] for bed in ward_beds)
        totals.update(counts)
        available.update(b["bed_type"] for b in ward_beds if b["status"] == Bed.Status.AVAILABLE)
        board["wards"].append(
            {
                "id": ward.pk,
                "code": ward.code,
                "name": ward.name,
                "ward_type": ward.ward_type,
                "building_name": ward.floor.building.name,
                "floor_name": ward.floor.name,
                "floor_level": ward.floor.level,
                "department": ward.department_id,
                "department_name": ward.department.name if ward.department else None,
                "gender_restriction": ward.gender_restriction,
                "age_group": ward.age_group,
                "can_change_status": change_scope.covers(
                    facility_id=chosen.pk, department_id=ward.department_id
                ),
                "bed_counts": dict(counts),
                "beds": ward_beds,
            }
        )
    board["bed_counts"] = dict(totals)
    board["available_by_type"] = dict(available)
    return board


def bed_history(bed) -> list[BedStatusChange]:
    return list(
        BedStatusChange.objects.filter(bed=bed).select_related("changed_by")[:HISTORY_LIMIT]
    )
