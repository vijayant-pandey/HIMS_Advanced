"""Equipment register API (HIMS-FAC-009; spec 4.12)."""

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.access_control.catalog import P
from apps.access_control.selectors import check_permission, get_permission_scope
from apps.features.catalog import F
from apps.features.services import disabled_facility_ids, require_enabled
from apps.organizations.selectors import get_deployment_organization
from common.idempotency.decorators import idempotent
from common.permissions import FACILITY, required_permission

from .. import services
from ..models import Equipment, EquipmentServiceRecord
from .serializers import (
    EquipmentCreateSerializer,
    EquipmentSerializer,
    EquipmentStatusSerializer,
    EquipmentUpdateSerializer,
    ServiceRecordCreateSerializer,
    ServiceRecordSerializer,
)

FILTERS = {
    "facility": "facility_id",
    "department": "department_id",
    "ward": "ward_id",
    "status": "status",
    "category": "category",
}
HISTORY_LIMIT = 50


def _visible(user, codename, queryset):
    """A hospital or facility grant shows everything there; a department grant shows only what
    is registered to that department."""
    scope = get_permission_scope(user, codename)
    if scope.org_wide:
        return queryset
    allowed = Q(facility_id__in=scope.facility_ids)
    for facility_id, department_id in scope.department_ids:
        allowed |= Q(facility_id=facility_id, department_id=department_id)
    return queryset.filter(allowed)


class EquipmentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = EquipmentSerializer
    permission_scope = FACILITY
    required_permissions = {
        "list": P.EQUIPMENT_VIEW,
        "retrieve": P.EQUIPMENT_VIEW,
        "history": P.EQUIPMENT_VIEW,
        "create": P.EQUIPMENT_MANAGE,
        "partial_update": P.EQUIPMENT_MANAGE,
        "change_status": P.EQUIPMENT_MANAGE,
        "record_service": P.EQUIPMENT_MANAGE,
    }
    http_method_names = ["get", "post", "patch", "head"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Equipment.objects.none()
        queryset = _visible(
            self.request.user,
            required_permission(self.request, self),
            Equipment.objects.select_related("facility", "department", "ward", "room"),
        ).order_by("facility__name", "asset_tag")
        if self.action != "list":
            return queryset
        params = self.request.query_params
        # Facilities where the hospital turned the register off (HIMS-ORG-004) are left out.
        queryset = queryset.exclude(
            facility_id__in=disabled_facility_ids(F.EQUIPMENT, request=self.request)
        )
        for param, lookup in FILTERS.items():
            if params.get(param):
                queryset = queryset.filter(**{lookup: params[param]})
        if params.get("due") in (services.OVERDUE, services.DUE_SOON):
            queryset = services.filter_due(queryset, params["due"])
        if params.get("search"):
            term = params["search"].strip()
            queryset = queryset.filter(
                Q(asset_tag__icontains=term)
                | Q(name__icontains=term)
                | Q(serial_number__icontains=term)
                | Q(manufacturer__icontains=term)
            )
        return queryset

    def get_permission_context(self, obj):
        return obj.facility_id, obj.department_id

    def get_object(self):
        obj = super().get_object()
        # One item in a facility where the register is off: explain instead of "not found".
        require_enabled(F.EQUIPMENT, facility_id=obj.facility_id, request=self.request)
        return obj

    def _check_department(self, facility_id, department):
        """Someone granted one department can only put equipment in that department."""
        check_permission(
            self.request.user,
            P.EQUIPMENT_MANAGE,
            facility_id=facility_id,
            department_id=department.pk if department else None,
        )

    @extend_schema(
        parameters=[OpenApiParameter(p, str) for p in FILTERS]
        + [
            OpenApiParameter("due", str, enum=[services.OVERDUE, services.DUE_SOON]),
            OpenApiParameter(
                "search", str, description="Part of the asset tag, name, serial or maker"
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=EquipmentCreateSerializer, responses={201: EquipmentSerializer})
    @idempotent("equipment.create")
    def create(self, request):
        serializer = EquipmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        facility = data.pop("facility")
        self._check_department(facility.pk, data.get("department"))
        require_enabled(F.EQUIPMENT, facility_id=facility.pk, request=request)
        item = services.create_equipment(
            actor=request.user,
            organization=get_deployment_organization(),
            facility=facility,
            request=request,
            **data,
        )
        return Response(EquipmentSerializer(item).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=EquipmentUpdateSerializer, responses=EquipmentSerializer)
    def partial_update(self, request, pk=None):
        item = self.get_object()
        serializer = EquipmentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if "department" in data:
            self._check_department(item.facility_id, data["department"])
        item = services.update_equipment(
            actor=request.user,
            equipment_id=item.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(EquipmentSerializer(item).data)

    @extend_schema(request=EquipmentStatusSerializer, responses=EquipmentSerializer)
    @action(detail=True, methods=["post"], url_path="status")
    @idempotent("equipment.status.change")
    def change_status(self, request, pk=None):
        item = self.get_object()
        serializer = EquipmentStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = services.change_status(
            actor=request.user, equipment_id=item.pk, request=request, **serializer.validated_data
        )
        return Response(EquipmentSerializer(item).data)

    @extend_schema(responses=ServiceRecordSerializer(many=True))
    @action(detail=True, methods=["get"], pagination_class=None)
    def history(self, request, pk=None):
        """The last 50 service, repair and calibration visits, newest first."""
        records = self.get_object().service_records.select_related("recorded_by")
        return Response(ServiceRecordSerializer(records[:HISTORY_LIMIT], many=True).data)

    @extend_schema(request=ServiceRecordCreateSerializer, responses={201: ServiceRecordSerializer})
    @action(detail=True, methods=["post"], url_path="service-records")
    @idempotent("equipment.service.record")
    def record_service(self, request, pk=None):
        item = self.get_object()
        serializer = ServiceRecordCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = services.record_service(
            actor=request.user,
            record=EquipmentServiceRecord(equipment=item, **serializer.validated_data),
            request=request,
        )
        return Response(ServiceRecordSerializer(record).data, status=status.HTTP_201_CREATED)
