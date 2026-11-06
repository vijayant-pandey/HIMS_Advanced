"""Rotas, on-call and leave API (spec 4.3; HIMS-STAFF-012).

Rota: seeing needs ``rota.view`` and planning ``rota.manage``, both for the department (a
department-scoped grant covers only that department). Shift types are hospital-wide, so changing
them needs a hospital-wide ``rota.manage``. Leave: approvers (``leave.approve`` for the
department) list, decide and record leave; everyone asks for and withdraws their own leave on
``/my-leave-requests/`` and sees their own shifts on ``/my-schedule/``.
"""

from datetime import timedelta
from uuid import UUID

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.catalog import P
from apps.access_control.selectors import check_permission, has_permission
from apps.facilities.models import Department
from apps.features.catalog import F
from apps.features.services import require_enabled
from apps.organizations.dates import hospital_today
from apps.staff.models import StaffMember
from common.exceptions import ConflictError
from common.idempotency.decorators import idempotent
from common.permissions import FACILITY

from .. import selectors, services
from ..models import LeaveRequest, ShiftType
from .serializers import (
    AddShiftsResultSerializer,
    AddShiftsSerializer,
    CancelSerializer,
    CopyWeekSerializer,
    LeaveCreateSerializer,
    LeaveDecisionSerializer,
    LeaveRequestSerializer,
    MyScheduleSerializer,
    RotaNowSerializer,
    RotaWeekSerializer,
    ShiftSerializer,
    ShiftTypeCreateSerializer,
    ShiftTypeSerializer,
    ShiftTypeUpdateSerializer,
)

LIST_LIMIT = 200


def _uuid(value, field: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise serializers.ValidationError({field: "Not a valid id."}) from exc


def _department(value, field: str = "department") -> Department:
    department = (
        Department.objects.select_related("facility").filter(pk=_uuid(value, field)).first()
    )
    if department is None:
        raise serializers.ValidationError({field: "No such department."})
    return department


def _staff(value, field: str = "staff") -> StaffMember:
    staff = StaffMember.objects.filter(pk=_uuid(value, field)).first()
    if staff is None:
        raise serializers.ValidationError({field: "No such staff member."})
    return staff


def _require(user, codename: str, department) -> None:
    check_permission(
        user, codename, facility_id=department.facility_id, department_id=department.pk
    )


def _monday(day):
    return day - timedelta(days=day.weekday())


def _result(created, skipped, *, nothing: str):
    if not created:
        reasons = "; ".join(f"{s['on_date']:%d %b}: {s['reason']}" for s in skipped[:5])
        raise ConflictError(f"{nothing} {reasons}".strip(), code="NOTHING_PLANNED")
    data = {"created": created, "skipped": skipped}
    return Response(AddShiftsResultSerializer(data).data, status=status.HTTP_201_CREATED)


class ShiftTypeViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Kinds of shift the hospital uses. Anyone who sees a rota sees them; a hospital-wide
    ``rota.manage`` grant adds and changes them (planned shifts keep their times)."""

    serializer_class = ShiftTypeSerializer
    pagination_class = None
    permission_scope = FACILITY
    required_permissions = {
        "list": P.ROTA_VIEW,
        "create": P.ROTA_MANAGE,
        "partial_update": P.ROTA_MANAGE,
    }

    def get_queryset(self):
        return ShiftType.objects.all()

    def get_permission_context(self, obj):
        return None, None  # hospital-wide: only a hospital-wide grant covers it

    @extend_schema(parameters=[OpenApiParameter("active", bool)])
    def list(self, request, *args, **kwargs):
        rows = self.get_queryset()
        if request.query_params.get("active") == "true":
            rows = rows.filter(is_active=True)
        return Response(ShiftTypeSerializer(rows, many=True).data)

    @extend_schema(request=ShiftTypeCreateSerializer, responses={201: ShiftTypeSerializer})
    @idempotent("shift_types.create")
    def create(self, request):
        check_permission(request.user, P.ROTA_MANAGE)
        serializer = ShiftTypeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shift_type = services.create_shift_type(
            actor=request.user, request=request, **serializer.validated_data
        )
        return Response(ShiftTypeSerializer(shift_type).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ShiftTypeUpdateSerializer, responses=ShiftTypeSerializer)
    def partial_update(self, request, pk=None):
        shift_type = self.get_object()
        serializer = ShiftTypeUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        updated = services.update_shift_type(
            actor=request.user,
            shift_type_id=shift_type.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(ShiftTypeSerializer(updated).data)


class ShiftViewSet(viewsets.GenericViewSet):
    """Plan, copy and cancel shifts and on-call (``rota.manage`` for the department)."""

    serializer_class = ShiftSerializer
    permission_scope = FACILITY
    required_permissions = {
        "create": P.ROTA_MANAGE,
        "cancel": P.ROTA_MANAGE,
        "copy_week": P.ROTA_MANAGE,
    }

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generating the API file: no database
            return selectors.shift_queryset().none()
        rows = selectors.shift_queryset()
        visible = selectors.scope_filter(self.request.user, P.ROTA_MANAGE)
        return rows if visible is None else rows.filter(visible)

    def get_permission_context(self, obj):
        return obj.facility_id, obj.department_id

    @extend_schema(request=AddShiftsSerializer, responses={201: AddShiftsResultSerializer})
    @idempotent("shifts.create")
    def create(self, request):
        """Plan one shift type for one person on one day, or on several days at once. Days that
        cannot be planned are listed in ``skipped`` with the reason."""
        serializer = AddShiftsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        department = _department(data["department"])
        _require(request.user, P.ROTA_MANAGE, department)
        shift_type = ShiftType.objects.filter(pk=data["shift_type"]).first()
        if shift_type is None:
            raise serializers.ValidationError({"shift_type": "No such shift type."})
        created, skipped = services.add_shifts(
            actor=request.user,
            staff=_staff(data["staff"]),
            department=department,
            shift_type=shift_type,
            from_date=data["from_date"],
            to_date=data.get("to_date") or data["from_date"],
            weekdays=data.get("weekdays"),
            note=data.get("note", ""),
            request=request,
        )
        return _result(created, skipped, nothing="Nothing was planned:")

    @extend_schema(request=CopyWeekSerializer, responses={201: AddShiftsResultSerializer})
    @action(detail=False, methods=["post"], url_path="copy-week")
    @idempotent("shifts.copy_week")
    def copy_week(self, request):
        """Repeat one week's shifts in a later week; people who cannot work a day are skipped."""
        serializer = CopyWeekSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        department = _department(data["department"])
        _require(request.user, P.ROTA_MANAGE, department)
        created, skipped = services.copy_week(
            actor=request.user,
            department=department,
            from_start=data["from_start"],
            to_start=data["to_start"],
            request=request,
        )
        if not created and not skipped:
            raise ConflictError("There are no planned shifts in that week.", code="NOTHING_TO_COPY")
        return _result(created, skipped, nothing="Nothing could be copied:")

    @extend_schema(request=CancelSerializer, responses=ShiftSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        shift = self.get_object()
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cancel_shift(
            actor=request.user,
            shift_id=shift.pk,
            version=serializer.validated_data["version"],
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(ShiftSerializer(selectors.shift_queryset().get(pk=shift.pk)).data)


class RotaWeekView(APIView):
    """One department's week: everyone posted there, their shifts and time away."""

    permission_scope = FACILITY
    required_permissions = {"get": P.ROTA_VIEW}

    @extend_schema(
        parameters=[
            OpenApiParameter("department", str, required=True),
            OpenApiParameter("start", str, description="First day (default: this Monday)"),
        ],
        responses=RotaWeekSerializer,
    )
    def get(self, request):
        department = _department(request.query_params.get("department", ""))
        _require(request.user, P.ROTA_VIEW, department)
        require_enabled(F.ROTAS, facility_id=department.facility_id, request=request)
        start = request.query_params.get("start")
        if start:
            start = serializers.DateField().to_internal_value(start)
        else:
            start = _monday(hospital_today(department.facility))
        scope = {"facility_id": department.facility_id, "department_id": department.pk}
        leave_details = has_permission(request.user, P.LEAVE_APPROVE, **scope)
        data = selectors.rota_week(department, start, leave_details=leave_details)
        data["can_manage"] = has_permission(request.user, P.ROTA_MANAGE, **scope)
        data["leave_details"] = leave_details
        return Response(RotaWeekSerializer(data).data)


class RotaNowView(APIView):
    """Who is on call and who is working right now, in the departments you may see."""

    permission_scope = FACILITY
    required_permissions = {"get": P.ROTA_VIEW}

    @extend_schema(parameters=[OpenApiParameter("facility", str)], responses=RotaNowSerializer)
    def get(self, request):
        facility = request.query_params.get("facility")
        data = selectors.happening_now(
            request.user,
            P.ROTA_VIEW,
            facility_id=_uuid(facility, "facility") if facility else None,
            request=request,
        )
        return Response(RotaNowSerializer(data).data)


class LeaveRequestViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Leave for approvers (``leave.approve`` for the department)."""

    serializer_class = LeaveRequestSerializer
    pagination_class = None
    permission_scope = FACILITY
    required_permissions = {
        "list": P.LEAVE_APPROVE,
        "retrieve": P.LEAVE_APPROVE,
        "create": P.LEAVE_APPROVE,
        "approve": P.LEAVE_APPROVE,
        "reject": P.LEAVE_APPROVE,
        "cancel": P.LEAVE_APPROVE,
    }

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generating the API file: no database
            return LeaveRequest.objects.none()
        rows = LeaveRequest.objects.select_related(
            "staff", "department", "requested_by", "decided_by"
        )
        visible = selectors.scope_filter(self.request.user, P.LEAVE_APPROVE)
        return rows if visible is None else rows.filter(visible)

    def get_permission_context(self, obj):
        return obj.facility_id, obj.department_id

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "status",
                str,
                enum=["waiting", "upcoming", "past", "all"],
                description="waiting (default) = to decide; upcoming = approved and not over; "
                "past = over, refused or cancelled",
            ),
            OpenApiParameter("department", str),
            OpenApiParameter("person", str, description="Staff member id"),
        ]
    )
    def list(self, request, *args, **kwargs):
        rows = self.get_queryset()
        today = hospital_today()
        wanted = request.query_params.get("status", "waiting")
        if wanted == "waiting":
            rows = rows.filter(status=LeaveRequest.Status.REQUESTED).order_by("start_date")
        elif wanted == "upcoming":
            rows = rows.filter(status=LeaveRequest.Status.APPROVED, end_date__gte=today)
            rows = rows.order_by("start_date")
        elif wanted == "past":
            rows = rows.filter(
                Q(end_date__lt=today)
                | Q(status__in=[LeaveRequest.Status.REJECTED, LeaveRequest.Status.CANCELLED])
            ).order_by("-start_date")
        elif wanted != "all":
            raise serializers.ValidationError({"status": "Use waiting, upcoming, past or all."})
        if request.query_params.get("department"):
            rows = rows.filter(
                department_id=_uuid(request.query_params["department"], "department")
            )
        if request.query_params.get("person"):
            rows = rows.filter(staff_id=_uuid(request.query_params["person"], "person"))
        return Response(LeaveRequestSerializer(rows[:LIST_LIMIT], many=True).data)

    @extend_schema(request=LeaveCreateSerializer, responses={201: LeaveRequestSerializer})
    @idempotent("leave_requests.create")
    def create(self, request):
        """Record leave for a staff member (e.g. sick leave phoned in). It still needs a
        decision, by someone other than that person."""
        serializer = LeaveCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not data.get("staff"):
            raise serializers.ValidationError({"staff": "Choose whose leave this is."})
        department = _department(data["department"])
        _require(request.user, P.LEAVE_APPROVE, department)
        leave = services.request_leave(
            actor=request.user,
            staff=_staff(data["staff"]),
            department=department,
            leave_type=data["leave_type"],
            start_date=data["start_date"],
            end_date=data["end_date"],
            reason=data.get("reason", ""),
            request=request,
        )
        return Response(LeaveRequestSerializer(leave).data, status=status.HTTP_201_CREATED)

    def _decided(self, pk):
        return LeaveRequestSerializer(self.get_queryset().get(pk=pk)).data

    @extend_schema(request=LeaveDecisionSerializer, responses=LeaveRequestSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        leave = self.get_object()
        serializer = LeaveDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.approve_leave(
            actor=request.user, leave_id=leave.pk, request=request, **serializer.validated_data
        )
        return Response(self._decided(leave.pk))

    @extend_schema(request=LeaveDecisionSerializer, responses=LeaveRequestSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        leave = self.get_object()
        serializer = LeaveDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reject_leave(
            actor=request.user,
            leave_id=leave.pk,
            version=serializer.validated_data["version"],
            note=serializer.validated_data["note"],
            request=request,
        )
        return Response(self._decided(leave.pk))

    @extend_schema(request=CancelSerializer, responses=LeaveRequestSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        leave = self.get_object()
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cancel_leave(
            actor=request.user,
            leave_id=leave.pk,
            version=serializer.validated_data["version"],
            reason=serializer.validated_data["reason"],
            as_approver=True,
            request=request,
        )
        return Response(self._decided(leave.pk))


def _own_staff(user) -> StaffMember:
    staff = StaffMember.objects.filter(user=user).first()
    if staff is None:
        raise ConflictError(
            "Your account has no staff record, so there is no rota or leave for you.",
            code="NO_STAFF_RECORD",
        )
    return staff


class MyScheduleView(APIView):
    """Your own postings, shifts (last week to six weeks ahead) and leave."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MyScheduleSerializer)
    def get(self, request):
        return Response(MyScheduleSerializer(selectors.my_schedule(request.user)).data)


class MyLeaveRequestsView(APIView):
    """Ask for your own leave; an approver for that department decides."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=LeaveCreateSerializer, responses={201: LeaveRequestSerializer})
    @idempotent("my_leave_requests.create")
    def post(self, request):
        serializer = LeaveCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        leave = services.request_leave(
            actor=request.user,
            staff=_own_staff(request.user),
            department=_department(data["department"]),
            leave_type=data["leave_type"],
            start_date=data["start_date"],
            end_date=data["end_date"],
            reason=data.get("reason", ""),
            request=request,
        )
        return Response(LeaveRequestSerializer(leave).data, status=status.HTTP_201_CREATED)


class MyLeaveCancelView(APIView):
    """Withdraw your own leave before it starts."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=CancelSerializer, responses=LeaveRequestSerializer)
    def post(self, request, pk):
        leave = get_object_or_404(LeaveRequest, pk=pk, staff=_own_staff(request.user))
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        leave = services.cancel_leave(
            actor=request.user,
            leave_id=leave.pk,
            version=serializer.validated_data["version"],
            reason=serializer.validated_data["reason"],
            as_approver=False,
            request=request,
        )
        return Response(LeaveRequestSerializer(leave).data)
