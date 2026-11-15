"""Doctor OPD schedules API (spec 4.6; HIMS-OPD-001).

Seeing sessions and free slots needs ``appointments.view`` and keeping them ``schedules.manage``,
both for the department (a department-scoped grant covers only that department). A holiday for a
whole facility needs a facility-wide (or hospital-wide) ``schedules.manage``. Doctors see their
own sessions on ``/my-opd-sessions/`` without either.
"""

from datetime import timedelta
from uuid import UUID

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.catalog import P
from apps.access_control.selectors import check_permission, get_permission_scope
from apps.facilities.models import Department, Facility
from apps.features.catalog import F
from apps.features.services import disabled_facility_ids, require_enabled
from apps.organizations.dates import hospital_today
from apps.rosters.selectors import scope_filter
from apps.staff.models import StaffMember
from common.idempotency.decorators import idempotent
from common.permissions import FACILITY

from .. import availability, selectors, services
from ..models import ScheduleException
from .serializers import (
    AddedExceptionSerializer,
    AddExceptionSerializer,
    AddSessionsSerializer,
    CancelExceptionSerializer,
    ChangeSessionSerializer,
    DepartmentWeekSerializer,
    DoctorDaySerializer,
    DoctorScheduleSerializer,
    EndSessionSerializer,
    MyOpdWeekSerializer,
    ScheduleExceptionSerializer,
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


def _date(value, field: str):
    try:
        return serializers.DateField().to_internal_value(value)
    except serializers.ValidationError as exc:
        raise serializers.ValidationError({field: exc.detail}) from exc


def _require(user, codename: str, department: Department) -> None:
    check_permission(
        user, codename, facility_id=department.facility_id, department_id=department.pk
    )


def _monday(day):
    return day - timedelta(days=day.weekday())


def _visible(viewset, rows):
    """Rows in the departments the person's grant for this action covers, without facilities
    where outpatient scheduling is off."""
    if getattr(viewset, "swagger_fake_view", False):  # generating the API file: no database
        return rows.none()
    codename = viewset.required_permissions.get(viewset.action, P.APPOINTMENTS_VIEW)
    visible = scope_filter(viewset.request.user, codename)
    if visible is not None:
        rows = rows.filter(visible)
    off = disabled_facility_ids(F.OUTPATIENT, request=viewset.request)
    return rows.exclude(facility_id__in=off) if off else rows


class DoctorScheduleViewSet(viewsets.GenericViewSet):
    """Doctors' weekly OPD sessions and one department's week."""

    serializer_class = DoctorScheduleSerializer
    pagination_class = None
    permission_scope = FACILITY
    required_permissions = {
        "list": P.APPOINTMENTS_VIEW,
        "week": P.APPOINTMENTS_VIEW,
        "create": P.SCHEDULES_MANAGE,
        "partial_update": P.SCHEDULES_MANAGE,
        "end": P.SCHEDULES_MANAGE,
    }

    def get_queryset(self):
        return _visible(self, selectors.schedule_queryset())

    def get_permission_context(self, obj):
        return obj.facility_id, obj.department_id

    @extend_schema(
        parameters=[
            OpenApiParameter("department", str),
            OpenApiParameter("staff", str, description="The doctor"),
            OpenApiParameter(
                "ended", bool, description="Also sessions that ended or were withdrawn"
            ),
        ]
    )
    def list(self, request):
        rows = self.get_queryset()
        if request.query_params.get("department"):
            rows = rows.filter(
                department_id=_uuid(request.query_params["department"], "department")
            )
        if request.query_params.get("staff"):
            rows = rows.filter(staff_id=_uuid(request.query_params["staff"], "staff"))
        if request.query_params.get("ended") != "true":
            rows = rows.filter(
                Q(valid_until__isnull=True) | Q(valid_until__gte=hospital_today()), is_active=True
            )
        rows = rows.order_by("department__name", "weekday", "start_time")[:LIST_LIMIT]
        return Response(DoctorScheduleSerializer(rows, many=True).data)

    @extend_schema(
        request=AddSessionsSerializer, responses={201: DoctorScheduleSerializer(many=True)}
    )
    @idempotent("doctor_schedules.create")
    def create(self, request):
        """Add a weekly session on one or more weekdays (all or none)."""
        serializer = AddSessionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        department = _department(data.pop("department"))
        _require(request.user, P.SCHEDULES_MANAGE, department)
        created = services.add_sessions(
            actor=request.user,
            staff=_staff(data.pop("staff")),
            department=department,
            request=request,
            **data,
        )
        return Response(
            DoctorScheduleSerializer(created, many=True).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(request=ChangeSessionSerializer, responses=DoctorScheduleSerializer)
    def partial_update(self, request, pk=None):
        """Slot length, extra bookings or the note. Days and hours: end it and add a new one."""
        schedule = self.get_object()
        serializer = ChangeSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        changed = services.change_session(
            actor=request.user,
            schedule_id=schedule.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(DoctorScheduleSerializer(changed).data)

    @extend_schema(request=EndSessionSerializer, responses=DoctorScheduleSerializer)
    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        """End a weekly session after a last day (a day before its first day withdraws it)."""
        schedule = self.get_object()
        serializer = EndSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.end_session(
            actor=request.user,
            schedule_id=schedule.pk,
            request=request,
            **serializer.validated_data,
        )
        return Response(DoctorScheduleSerializer(selectors.schedule_queryset().get(pk=pk)).data)

    @extend_schema(
        parameters=[
            OpenApiParameter("department", str, required=True),
            OpenApiParameter("start", str, description="First day (default: this Monday)"),
        ],
        responses=DepartmentWeekSerializer,
    )
    @action(detail=False, methods=["get"])
    def week(self, request):
        """One department's doctors over seven days: each day's sessions, what takes them off
        (OPD leave, approved leave on the Leave page, holidays), and the exceptions."""
        department = _department(request.query_params.get("department", ""))
        _require(request.user, P.APPOINTMENTS_VIEW, department)
        require_enabled(F.OUTPATIENT, facility_id=department.facility_id, request=request)
        start = request.query_params.get("start")
        start = _date(start, "start") if start else _monday(hospital_today(department.facility))
        manage = get_permission_scope(request.user, P.SCHEDULES_MANAGE)
        details = manage.covers(facility_id=department.facility_id, department_id=department.pk)
        data = selectors.department_week(department, start, details=details)
        data["can_manage"] = details
        data["can_close_facility"] = manage.covers(facility_id=department.facility_id)
        data["details"] = details
        return Response(DepartmentWeekSerializer(data, context={"manage_scope": manage}).data)


class ScheduleExceptionViewSet(viewsets.GenericViewSet):
    """A doctor away, a holiday or an extra session."""

    serializer_class = ScheduleExceptionSerializer
    pagination_class = None
    permission_scope = FACILITY
    required_permissions = {
        "list": P.APPOINTMENTS_VIEW,
        "create": P.SCHEDULES_MANAGE,
        "cancel": P.SCHEDULES_MANAGE,
    }

    def get_queryset(self):
        return _visible(self, selectors.exception_queryset())

    def get_permission_context(self, obj):
        return obj.facility_id, obj.department_id

    def _context(self):
        return {"manage_scope": get_permission_scope(self.request.user, P.SCHEDULES_MANAGE)}

    @extend_schema(
        parameters=[
            OpenApiParameter("department", str),
            OpenApiParameter("staff", str, description="The doctor"),
            OpenApiParameter("kind", str, enum=[k for k, _ in ScheduleException.Kind.choices]),
            OpenApiParameter("upcoming", bool, description="Only those not over (default true)"),
        ]
    )
    def list(self, request):
        rows = self.get_queryset().filter(status=ScheduleException.Status.ACTIVE)
        params = request.query_params
        if params.get("department"):
            rows = rows.filter(department_id=_uuid(params["department"], "department"))
        if params.get("staff"):
            rows = rows.filter(staff_id=_uuid(params["staff"], "staff"))
        if params.get("kind"):
            rows = rows.filter(kind=params["kind"])
        if params.get("upcoming", "true") != "false":
            rows = rows.filter(end_date__gte=hospital_today())
        rows = rows.order_by("start_date", "start_time")[:LIST_LIMIT]
        return Response(ScheduleExceptionSerializer(rows, many=True, context=self._context()).data)

    @extend_schema(request=AddExceptionSerializer, responses={201: AddedExceptionSerializer})
    @idempotent("schedule_exceptions.create")
    def create(self, request):
        """Record a doctor away, a holiday (a department, or the whole facility) or an extra
        session. The answer lists the sessions it takes off."""
        serializer = AddExceptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        department = _department(data["department"]) if data.get("department") else None
        if department is not None:
            facility = department.facility
            _require(request.user, P.SCHEDULES_MANAGE, department)
        elif data["kind"] == ScheduleException.Kind.HOLIDAY and data.get("facility"):
            facility = Facility.objects.filter(pk=data["facility"]).first()
            if facility is None:
                raise serializers.ValidationError({"facility": "No such facility."})
            check_permission(request.user, P.SCHEDULES_MANAGE, facility_id=facility.pk)
        else:
            raise serializers.ValidationError({"department": "Choose the department."})
        item, affected = services.add_exception(
            actor=request.user,
            kind=data["kind"],
            facility=facility,
            department=department,
            staff=_staff(data["staff"]) if data.get("staff") else None,
            start_date=data["start_date"],
            end_date=data.get("end_date"),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            slot_minutes=data.get("slot_minutes"),
            extra_bookings_allowed=data.get("extra_bookings_allowed"),
            reason=data["reason"],
            request=request,
        )
        body = {"exception": item, "affected": [availability.session_out(s) for s in affected]}
        return Response(
            AddedExceptionSerializer(body, context=self._context()).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=CancelExceptionSerializer, responses=ScheduleExceptionSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancel a doctor away, a holiday or an extra session that is not over; the sessions
        come back. It stays on record as cancelled."""
        item = self.get_object()
        serializer = CancelExceptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cancel_exception(
            actor=request.user, exception_id=item.pk, request=request, **serializer.validated_data
        )
        return Response(
            ScheduleExceptionSerializer(
                selectors.exception_queryset().get(pk=pk), context=self._context()
            ).data
        )


class DoctorAvailabilityView(APIView):
    """One doctor's sessions on one day with each open slot, in the departments you may see."""

    permission_scope = FACILITY
    required_permissions = {"get": P.APPOINTMENTS_VIEW}

    @extend_schema(
        parameters=[
            OpenApiParameter("doctor", str, required=True, description="Staff member id"),
            OpenApiParameter("date", str, required=True),
            OpenApiParameter("department", str),
        ],
        responses=DoctorDaySerializer,
    )
    def get(self, request):
        params = request.query_params
        doctor = _staff(params.get("doctor", ""), "doctor")
        day = _date(params.get("date", ""), "date")
        department = None
        if params.get("department"):
            department = _department(params["department"])
            _require(request.user, P.APPOINTMENTS_VIEW, department)
            require_enabled(F.OUTPATIENT, facility_id=department.facility_id, request=request)
        scope = get_permission_scope(request.user, P.APPOINTMENTS_VIEW)
        manage = get_permission_scope(request.user, P.SCHEDULES_MANAGE)
        off = disabled_facility_ids(F.OUTPATIENT, request=request)
        data = selectors.doctor_day(doctor, day, department=department, details=False)
        shown = []
        for session in data["sessions"]:
            where = {
                "facility_id": session["facility_id"],
                "department_id": session["department_id"],
            }
            if session["facility_id"] in off or not scope.covers(**where):
                continue
            if not manage.covers(**where):  # an away note is for the people keeping schedules
                for block in session["off"]:
                    if block["kind"] == "leave":
                        block["reason"] = "Away"
            shown.append(session)
        data["sessions"] = shown
        return Response(DoctorDaySerializer(data).data)


class MyOpdSessionsView(APIView):
    """Your own OPD sessions over a week, in every department."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[OpenApiParameter("start", str, description="First day (default: this Monday)")],
        responses=MyOpdWeekSerializer,
    )
    def get(self, request):
        start = request.query_params.get("start")
        start = _date(start, "start") if start else _monday(hospital_today())
        staff = StaffMember.objects.filter(user=request.user).first()
        if staff is None:
            return Response(
                MyOpdWeekSerializer({"has_staff_record": False, "start": start, "days": []}).data
            )
        data = selectors.my_week(staff, start)
        data["has_staff_record"] = True
        return Response(MyOpdWeekSerializer(data).data)
