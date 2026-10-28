from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from apps.access_control.catalog import P
from apps.access_control.selectors import check_permission
from common.idempotency.decorators import idempotent
from common.permissions import FACILITY, filter_by_facility_scope

from .. import services
from ..models import Department, Facility
from .serializers import (
    DepartmentCreateSerializer,
    DepartmentSerializer,
    DepartmentUpdateSerializer,
    FacilityCreateSerializer,
    FacilitySerializer,
    FacilityUpdateSerializer,
    department_counts,
    facility_counts,
)


class FacilityViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = FacilitySerializer
    permission_scope = FACILITY
    required_permissions = {
        "list": P.FACILITIES_VIEW,
        "retrieve": P.FACILITIES_VIEW,
        "create": P.FACILITIES_MANAGE,
        "partial_update": P.FACILITIES_MANAGE,
    }
    http_method_names = ["get", "post", "patch", "head"]

    def get_queryset(self):
        queryset = filter_by_facility_scope(self, Facility.objects.all(), facility_field="pk")
        return facility_counts(queryset).order_by("name")  # counting drops Meta.ordering

    def get_permission_context(self, obj):
        return obj.pk, None

    @extend_schema(request=FacilityCreateSerializer, responses={201: FacilitySerializer})
    @idempotent("facilities.create")
    def create(self, request):
        # Creating a branch is an organization-level decision.
        check_permission(request.user, P.FACILITIES_MANAGE)
        serializer = FacilityCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        facility = services.create_facility(
            actor=request.user, request=request, **serializer.validated_data
        )
        return Response(FacilitySerializer(facility).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=FacilityUpdateSerializer, responses=FacilitySerializer)
    def partial_update(self, request, pk=None):
        facility = self.get_object()
        serializer = FacilityUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        facility = services.update_facility(
            actor=request.user,
            facility_id=facility.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(FacilitySerializer(facility).data)


class DepartmentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = DepartmentSerializer
    permission_scope = FACILITY
    required_permissions = {
        "list": P.DEPARTMENTS_VIEW,
        "retrieve": P.DEPARTMENTS_VIEW,
        "create": P.DEPARTMENTS_MANAGE,
        "partial_update": P.DEPARTMENTS_MANAGE,
    }
    http_method_names = ["get", "post", "patch", "head"]

    def get_queryset(self):
        queryset = filter_by_facility_scope(self, Department.objects.select_related("facility"))
        facility_id = self.request.query_params.get("facility")
        if facility_id:
            queryset = queryset.filter(facility_id=facility_id)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return department_counts(queryset).order_by("facility__name", "name")

    def get_permission_context(self, obj):
        return obj.facility_id, obj.pk

    @extend_schema(
        parameters=[
            OpenApiParameter("facility", str, description="Filter by facility ID"),
            OpenApiParameter("status", str, description="active or inactive"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=DepartmentCreateSerializer, responses={201: DepartmentSerializer})
    @idempotent("departments.create")
    def create(self, request):
        serializer = DepartmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        facility = data.pop("facility")
        check_permission(request.user, P.DEPARTMENTS_MANAGE, facility_id=facility.pk)
        department = services.create_department(
            actor=request.user, facility=facility, request=request, **data
        )
        return Response(DepartmentSerializer(department).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=DepartmentUpdateSerializer, responses=DepartmentSerializer)
    def partial_update(self, request, pk=None):
        department = self.get_object()
        serializer = DepartmentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        department = services.update_department(
            actor=request.user,
            department_id=department.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(DepartmentSerializer(department).data)
