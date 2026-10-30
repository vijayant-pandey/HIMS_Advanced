from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.access_control.catalog import P
from apps.access_control.selectors import check_permission
from common.idempotency.decorators import idempotent
from common.permissions import FACILITY, filter_by_facility_scope

from .. import services
from ..models import Department, DepartmentService, Facility
from .serializers import (
    DepartmentCreateSerializer,
    DepartmentDetailSerializer,
    DepartmentHoursSerializer,
    DepartmentSerializer,
    DepartmentServiceCreateSerializer,
    DepartmentServiceSerializer,
    DepartmentServiceUpdateSerializer,
    DepartmentUpdateSerializer,
    FacilityCreateSerializer,
    FacilitySerializer,
    FacilityUpdateSerializer,
    HeadCandidateSerializer,
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
        "head_candidates": P.DEPARTMENTS_MANAGE,
        "set_hours": P.DEPARTMENTS_MANAGE,
        "add_service": P.DEPARTMENTS_MANAGE,
    }
    http_method_names = ["get", "post", "patch", "put", "head"]

    def get_serializer_class(self):
        return DepartmentDetailSerializer if self.action == "retrieve" else DepartmentSerializer

    def get_queryset(self):
        queryset = filter_by_facility_scope(
            self, Department.objects.select_related("facility", "head")
        )
        if self.action == "retrieve":
            queryset = queryset.prefetch_related("services", "hours")
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

    @extend_schema(responses=HeadCandidateSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="head-candidates", pagination_class=None)
    def head_candidates(self, request, pk=None):
        """Working staff currently posted in this department: the people who can be its head."""
        from apps.facilities.closing import current_postings_q
        from apps.staff.models import StaffDepartmentAssignment

        department = self.get_object()
        today = timezone.localdate()
        postings = (
            StaffDepartmentAssignment.objects.filter(
                current_postings_q(), department=department, valid_from__lte=today
            )
            .filter(staff__employment_status__in=["active", "on_leave"])
            .select_related("staff", "designation")
            .order_by("-designation__seniority", "staff__family_name")
        )
        seen, rows = set(), []
        for posting in postings:
            if posting.staff_id in seen:
                continue
            seen.add(posting.staff_id)
            staff = posting.staff
            rows.append(
                {
                    "id": staff.pk,
                    "name": f"{staff.given_name} {staff.family_name}",
                    "designation": posting.designation.name if posting.designation_id else None,
                }
            )
        return Response(HeadCandidateSerializer(rows, many=True).data)

    @extend_schema(request=DepartmentHoursSerializer, responses=DepartmentDetailSerializer)
    @action(detail=True, methods=["put"], url_path="hours")
    def set_hours(self, request, pk=None):
        """Replace the weekly opening hours (and the open-24-hours switch) in one go."""
        department = self.get_object()
        serializer = DepartmentHoursSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.set_department_hours(
            actor=request.user,
            department_id=department.pk,
            version=data["version"],
            open_24_hours=data["open_24_hours"],
            sessions=data["sessions"],
            request=request,
        )
        return Response(DepartmentDetailSerializer(self.get_queryset().get(pk=department.pk)).data)

    @extend_schema(
        request=DepartmentServiceCreateSerializer, responses={201: DepartmentServiceSerializer}
    )
    @action(detail=True, methods=["post"], url_path="services")
    @idempotent("departments.services.create")
    def add_service(self, request, pk=None):
        department = self.get_object()
        serializer = DepartmentServiceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = services.create_department_service(
            actor=request.user, department=department, request=request, **serializer.validated_data
        )
        return Response(DepartmentServiceSerializer(service).data, status=status.HTTP_201_CREATED)


class DepartmentServiceViewSet(viewsets.GenericViewSet):
    """Change or switch off one department service (never deleted)."""

    queryset = DepartmentService.objects.select_related("department")
    serializer_class = DepartmentServiceSerializer
    permission_scope = FACILITY
    required_permissions = {"partial_update": P.DEPARTMENTS_MANAGE}
    http_method_names = ["patch", "head"]

    def get_queryset(self):
        return filter_by_facility_scope(
            self, self.queryset, facility_field="department__facility_id"
        )

    def get_permission_context(self, obj):
        return obj.department.facility_id, obj.department_id

    @extend_schema(request=DepartmentServiceUpdateSerializer, responses=DepartmentServiceSerializer)
    def partial_update(self, request, pk=None):
        service = self.get_object()
        serializer = DepartmentServiceUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        service = services.update_department_service(
            actor=request.user,
            service_id=service.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(DepartmentServiceSerializer(service).data)
