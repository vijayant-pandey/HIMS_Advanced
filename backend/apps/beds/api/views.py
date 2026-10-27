"""Bed API and the facility location tree (HIMS-FAC-004)."""

from collections import Counter

from django.db.models import Prefetch
from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.catalog import P
from apps.access_control.selectors import check_permission, get_permission_scope
from apps.facilities import location_services
from apps.facilities.models import Building, Facility, Floor, Room, Ward
from common.idempotency.decorators import idempotent
from common.permissions import FACILITY, filter_by_facility_scope

from .. import services
from ..models import Bed
from .serializers import (
    BedCreateSerializer,
    BedSerializer,
    BedStatusChangeSerializer,
    BedUpdateSerializer,
    BulkBedsSerializer,
    FacilityLocationsSerializer,
)

BED_FILTERS = {
    "facility": "facility_id",
    "ward": "ward_id",
    "room": "room_id",
    "status": "status",
    "bed_type": "bed_type",
}


class BedViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = BedSerializer
    permission_scope = FACILITY
    required_permissions = {
        "list": P.LOCATIONS_VIEW,
        "retrieve": P.LOCATIONS_VIEW,
        "create": P.LOCATIONS_MANAGE,
        "partial_update": P.LOCATIONS_MANAGE,
        "bulk": P.LOCATIONS_MANAGE,
        "change_status": P.BEDS_STATUS_MANAGE,
    }
    http_method_names = ["get", "post", "patch", "head"]

    def get_queryset(self):
        queryset = filter_by_facility_scope(self, Bed.objects.all())
        for param, lookup in BED_FILTERS.items():
            value = self.request.query_params.get(param)
            if value:
                queryset = queryset.filter(**{lookup: value})
        if self.request.query_params.get("active") == "true":
            queryset = queryset.filter(is_active=True)
        return queryset

    def get_permission_context(self, obj):
        return obj.facility_id, None

    @extend_schema(
        parameters=[OpenApiParameter(p, str) for p in BED_FILTERS]
        + [OpenApiParameter("active", str, description="'true' = active only")]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=BedCreateSerializer, responses={201: BedSerializer})
    @idempotent("beds.create")
    def create(self, request):
        serializer = BedCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        room = serializer.validated_data["room"]
        check_permission(request.user, P.LOCATIONS_MANAGE, facility_id=room.facility_id)
        bed = location_services.create_location(
            Bed, actor=request.user, request=request, **serializer.validated_data
        )
        return Response(BedSerializer(bed).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=BedUpdateSerializer, responses=BedSerializer)
    def partial_update(self, request, pk=None):
        bed = self.get_object()
        serializer = BedUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        bed = location_services.update_location(
            Bed,
            actor=request.user,
            pk=bed.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(BedSerializer(bed).data)

    @extend_schema(request=BedStatusChangeSerializer, responses=BedSerializer)
    @action(detail=True, methods=["post"], url_path="status")
    @idempotent("beds.status.change")
    def change_status(self, request, pk=None):
        bed = self.get_object()
        serializer = BedStatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bed = services.change_bed_status(
            actor=request.user, bed_id=bed.pk, request=request, **serializer.validated_data
        )
        return Response(BedSerializer(bed).data)

    @extend_schema(request=BulkBedsSerializer, responses={201: BedSerializer(many=True)})
    @action(detail=False, methods=["post"])
    @idempotent("beds.bulk_create")
    def bulk(self, request):
        serializer = BulkBedsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        room = serializer.validated_data["room"]
        check_permission(request.user, P.LOCATIONS_MANAGE, facility_id=room.facility_id)
        beds = services.create_beds_in_room(
            actor=request.user, request=request, **serializer.validated_data
        )
        return Response(BedSerializer(beds, many=True).data, status=status.HTTP_201_CREATED)


class FacilityLocationsView(APIView):
    """The whole building → floor → ward → room → bed structure of one facility.

    One request with five queries, used by the Locations screen and the future bed board.
    """

    permission_scope = FACILITY
    required_permissions = {"get": P.LOCATIONS_VIEW}

    @extend_schema(
        operation_id="facilities_locations_retrieve",
        parameters=[OpenApiParameter("active", str, description="'true' = active only")],
        responses=FacilityLocationsSerializer,
    )
    def get(self, request, pk):
        scope = get_permission_scope(request.user, P.LOCATIONS_VIEW)
        if not Facility.objects.filter(pk=pk).exists() or not scope.covers(
            facility_id=pk, department_id=None
        ):
            raise Http404  # out of scope looks the same as missing
        active_only = request.query_params.get("active") == "true"

        def nodes(model):
            queryset = model.objects.all()
            return queryset.filter(is_active=True) if active_only else queryset

        beds = nodes(Bed).order_by("code")
        rooms = nodes(Room).order_by("code").prefetch_related(Prefetch("beds", queryset=beds))
        wards = (
            nodes(Ward)
            .select_related("department")
            .order_by("code")
            .prefetch_related(Prefetch("rooms", queryset=rooms))
        )
        floors = nodes(Floor).order_by("level").prefetch_related(Prefetch("wards", queryset=wards))
        buildings = (
            nodes(Building)
            .filter(facility_id=pk)
            .order_by("code")
            .prefetch_related(Prefetch("floors", queryset=floors))
        )

        totals = Counter()
        tree = []
        for building in buildings:
            building_floors = []
            for floor in building.floors.all():
                floor_wards = []
                for ward in floor.wards.all():
                    counts = Counter()
                    ward_rooms = []
                    for room in ward.rooms.all():
                        room_beds = [
                            {
                                "id": bed.pk,
                                "code": bed.code,
                                "bed_type": bed.bed_type,
                                "status": bed.status,
                                "status_reason": bed.status_reason,
                                "is_active": bed.is_active,
                                "version": bed.version,
                            }
                            for bed in room.beds.all()
                        ]
                        counts.update(bed["status"] for bed in room_beds if bed["is_active"])
                        ward_rooms.append(
                            {
                                "id": room.pk,
                                "code": room.code,
                                "name": room.name,
                                "room_type": room.room_type,
                                "is_isolation_capable": room.is_isolation_capable,
                                "is_active": room.is_active,
                                "version": room.version,
                                "beds": room_beds,
                            }
                        )
                    totals.update(counts)
                    floor_wards.append(
                        {
                            "id": ward.pk,
                            "code": ward.code,
                            "name": ward.name,
                            "ward_type": ward.ward_type,
                            "department": ward.department_id,
                            "department_name": ward.department.name if ward.department else None,
                            "gender_restriction": ward.gender_restriction,
                            "age_group": ward.age_group,
                            "is_active": ward.is_active,
                            "version": ward.version,
                            "bed_counts": dict(counts),
                            "rooms": ward_rooms,
                        }
                    )
                building_floors.append(
                    {
                        "id": floor.pk,
                        "level": floor.level,
                        "name": floor.name,
                        "is_active": floor.is_active,
                        "version": floor.version,
                        "wards": floor_wards,
                    }
                )
            tree.append(
                {
                    "id": building.pk,
                    "code": building.code,
                    "name": building.name,
                    "is_active": building.is_active,
                    "version": building.version,
                    "floors": building_floors,
                }
            )
        data = {"facility": pk, "bed_counts": dict(totals), "buildings": tree}
        return Response(FacilityLocationsSerializer(data).data)
