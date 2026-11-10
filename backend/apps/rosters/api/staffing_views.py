"""Minimum staffing and leave balances API (HIMS-STAFF-015, HIMS-STAFF-013; spec 4.3)."""

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.catalog import P
from apps.access_control.selectors import check_permission
from apps.features.catalog import F
from apps.features.services import require_enabled
from apps.organizations.dates import hospital_today
from apps.staff.models import StaffMember
from apps.staff.selectors import limit_to_visible
from common.idempotency.decorators import idempotent
from common.permissions import FACILITY, ORGANIZATION

from .. import balances, selectors, staffing
from ..models import (
    LeaveBalanceAdjustment,
    LeaveEntitlement,
    LeaveRequest,
    ShiftType,
    StaffingRequirement,
)
from .serializers import LeaveBalanceSerializer
from .views import _department, _staff, _uuid

WORKING = (StaffMember.EmploymentStatus.ACTIVE, StaffMember.EmploymentStatus.ON_LEAVE)


class StaffingRequirementSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    shift_type_name = serializers.CharField(source="shift_type.name", read_only=True)
    staff_type_label = serializers.SerializerMethodField()
    applies_on_label = serializers.CharField(source="get_applies_on_display", read_only=True)

    def get_staff_type_label(self, row) -> str:
        return row.get_staff_type_display() if row.staff_type else "Anyone"

    class Meta:
        model = StaffingRequirement
        fields = [
            "id",
            "department",
            "department_name",
            "shift_type",
            "shift_type_name",
            "staff_type",
            "staff_type_label",
            "applies_on",
            "applies_on_label",
            "minimum",
            "is_active",
            "version",
        ]
        read_only_fields = fields


class StaffingRequirementCreateSerializer(serializers.Serializer):
    department = serializers.UUIDField()
    shift_type = serializers.UUIDField()
    minimum = serializers.IntegerField(min_value=1, max_value=999)
    staff_type = serializers.ChoiceField(
        StaffMember.StaffType.choices,
        required=False,
        allow_blank=True,
        default="",
        help_text="Blank means anyone on the shift counts",
    )
    applies_on = serializers.ChoiceField(
        StaffingRequirement.AppliesOn.choices,
        required=False,
        default=StaffingRequirement.AppliesOn.EVERY_DAY,
    )


class StaffingRequirementUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    minimum = serializers.IntegerField(min_value=1, max_value=999, required=False)
    is_active = serializers.BooleanField(required=False)


class StaffingRequirementViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The hospital's minimum people per shift. Seeing needs ``rota.view``, setting ``rota.manage``,
    both for the department."""

    serializer_class = StaffingRequirementSerializer
    pagination_class = None
    permission_scope = FACILITY
    required_permissions = {
        "list": P.ROTA_VIEW,
        "create": P.ROTA_MANAGE,
        "partial_update": P.ROTA_MANAGE,
    }
    http_method_names = ["get", "post", "patch", "head"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generating the API file: no database
            return StaffingRequirement.objects.none()
        rows = StaffingRequirement.objects.select_related("department", "shift_type").order_by(
            "shift_type__start_time", "staff_type", "applies_on"
        )
        codename = P.ROTA_VIEW if self.action == "list" else P.ROTA_MANAGE
        visible = selectors.scope_filter(self.request.user, codename)
        return rows if visible is None else rows.filter(visible)

    def get_permission_context(self, obj):
        return obj.facility_id, obj.department_id

    @extend_schema(parameters=[OpenApiParameter("department", str)])
    def list(self, request, *args, **kwargs):
        rows = self.get_queryset()
        if request.query_params.get("department"):
            rows = rows.filter(
                department_id=_uuid(request.query_params["department"], "department")
            )
        return Response(StaffingRequirementSerializer(rows, many=True).data)

    @extend_schema(
        request=StaffingRequirementCreateSerializer, responses={201: StaffingRequirementSerializer}
    )
    @idempotent("staffing_requirements.create")
    def create(self, request):
        serializer = StaffingRequirementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        department = _department(data.pop("department"))
        check_permission(
            request.user,
            P.ROTA_MANAGE,
            facility_id=department.facility_id,
            department_id=department.pk,
        )
        require_enabled(F.ROTAS, facility_id=department.facility_id, request=request)
        shift_type = ShiftType.objects.filter(pk=data.pop("shift_type")).first()
        if shift_type is None:
            raise serializers.ValidationError({"shift_type": "No such shift type."})
        row = staffing.create_requirement(
            actor=request.user,
            department=department,
            shift_type=shift_type,
            request=request,
            **data,
        )
        return Response(StaffingRequirementSerializer(row).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=StaffingRequirementUpdateSerializer, responses=StaffingRequirementSerializer
    )
    def partial_update(self, request, pk=None):
        row = self.get_object()
        serializer = StaffingRequirementUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        row = staffing.update_requirement(
            actor=request.user,
            requirement_id=row.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(StaffingRequirementSerializer(row).data)


class PersonBalancesSerializer(serializers.Serializer):
    staff_id = serializers.UUIDField()
    name = serializers.CharField()
    balances = LeaveBalanceSerializer(many=True)


class DepartmentBalancesSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    year_label = serializers.CharField()
    people = PersonBalancesSerializer(many=True)


class LeaveBalancesView(APIView):
    """Everyone working in a department and what is left of each kind of leave. For people who
    decide leave there, who already see the kinds of leave."""

    permission_scope = FACILITY
    required_permissions = {"get": P.LEAVE_APPROVE}

    @extend_schema(
        parameters=[
            OpenApiParameter("department", str, required=True),
            OpenApiParameter("year", int, description="Leave year (default: this one)"),
        ],
        responses=DepartmentBalancesSerializer,
    )
    def get(self, request):
        department = _department(request.query_params.get("department", ""))
        check_permission(
            request.user,
            P.LEAVE_APPROVE,
            facility_id=department.facility_id,
            department_id=department.pk,
        )
        require_enabled(F.ROTAS, facility_id=department.facility_id, request=request)
        month = balances.start_month()
        year = balances.current_year(month)
        if request.query_params.get("year"):
            year = serializers.IntegerField(min_value=2000, max_value=2100).run_validation(
                request.query_params["year"]
            )
        today = hospital_today(department.facility)
        people = list(
            StaffMember.objects.filter(
                Q(department_assignments__valid_until__isnull=True)
                | Q(department_assignments__valid_until__gte=today),
                department_assignments__department=department,
                department_assignments__valid_from__lte=today,
                employment_status__in=WORKING,
            )
            .distinct()
            .order_by("family_name", "given_name")
        )
        found = balances.balances_for(people, year=year)
        return Response(
            DepartmentBalancesSerializer(
                {
                    "year": year,
                    "year_label": balances.year_label(year, month),
                    "people": [
                        {
                            "staff_id": person.pk,
                            "name": f"{person.given_name} {person.family_name}",
                            "balances": found[person.pk],
                        }
                        for person in people
                    ],
                }
            ).data
        )


class LeaveEntitlementSerializer(serializers.ModelSerializer):
    leave_type_label = serializers.CharField(source="get_leave_type_display", read_only=True)
    year_label = serializers.SerializerMethodField()
    can_change = serializers.SerializerMethodField(
        help_text="False for a row started in an earlier year: add a new one instead"
    )

    def get_year_label(self, row) -> str:
        return balances.year_label(row.from_year, balances.start_month())

    def get_can_change(self, row) -> bool:
        return row.from_year >= balances.current_year()

    class Meta:
        model = LeaveEntitlement
        fields = [
            "id",
            "leave_type",
            "leave_type_label",
            "from_year",
            "year_label",
            "days",
            "max_carry_over",
            "prorate_on_joining",
            "tracked",
            "can_change",
            "version",
        ]
        read_only_fields = fields


class LeaveEntitlementCreateSerializer(serializers.Serializer):
    leave_type = serializers.ChoiceField(LeaveRequest.LeaveType.choices)
    from_year = serializers.IntegerField(min_value=2000, max_value=2100)
    days = serializers.IntegerField(min_value=0, max_value=366)
    max_carry_over = serializers.IntegerField(min_value=0, max_value=366, required=False, default=0)
    prorate_on_joining = serializers.BooleanField(required=False, default=True)
    tracked = serializers.BooleanField(required=False, default=True)


class LeaveEntitlementUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    days = serializers.IntegerField(min_value=0, max_value=366, required=False)
    max_carry_over = serializers.IntegerField(min_value=0, max_value=366, required=False)
    prorate_on_joining = serializers.BooleanField(required=False)
    tracked = serializers.BooleanField(required=False)


class LeaveEntitlementViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Days per year for each kind of leave. Approvers read them; ``leave.policy.manage``
    (hospital-wide) sets them."""

    serializer_class = LeaveEntitlementSerializer
    pagination_class = None
    required_permissions = {
        "list": P.LEAVE_APPROVE,
        "create": P.LEAVE_POLICY_MANAGE,
        "partial_update": P.LEAVE_POLICY_MANAGE,
    }
    http_method_names = ["get", "post", "patch", "head"]

    @property
    def permission_scope(self):
        return FACILITY if getattr(self, "action", None) == "list" else ORGANIZATION

    def get_queryset(self):
        return LeaveEntitlement.objects.order_by("leave_type", "-from_year")

    def get_permission_context(self, obj):
        return None, None  # hospital-wide

    @extend_schema(
        request=LeaveEntitlementCreateSerializer, responses={201: LeaveEntitlementSerializer}
    )
    @idempotent("leave_entitlements.create")
    def create(self, request):
        serializer = LeaveEntitlementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = balances.create_entitlement(
            actor=request.user, request=request, **serializer.validated_data
        )
        return Response(LeaveEntitlementSerializer(row).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=LeaveEntitlementUpdateSerializer, responses=LeaveEntitlementSerializer)
    def partial_update(self, request, pk=None):
        row = self.get_object()
        serializer = LeaveEntitlementUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        row = balances.update_entitlement(
            actor=request.user,
            entitlement_id=row.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(LeaveEntitlementSerializer(row).data)


class LeaveAdjustmentSerializer(serializers.ModelSerializer):
    leave_type_label = serializers.CharField(source="get_leave_type_display", read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.display_name", read_only=True, allow_null=True, default=None
    )

    class Meta:
        model = LeaveBalanceAdjustment
        fields = [
            "id",
            "staff",
            "leave_type",
            "leave_type_label",
            "leave_year",
            "days",
            "reason",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = fields


class LeaveAdjustmentCreateSerializer(serializers.Serializer):
    staff = serializers.UUIDField()
    leave_type = serializers.ChoiceField(LeaveRequest.LeaveType.choices)
    leave_year = serializers.IntegerField(min_value=2000, max_value=2100)
    days = serializers.IntegerField(
        min_value=-366, max_value=366, help_text="Plus adds days, minus takes them away"
    )
    reason = serializers.CharField(max_length=255)


class LeaveAdjustmentViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Days added to or taken from a balance. Append-only. Reading follows ``leave.approve``;
    adding needs ``leave.policy.manage``."""

    serializer_class = LeaveAdjustmentSerializer
    pagination_class = None
    required_permissions = {"list": P.LEAVE_APPROVE, "create": P.LEAVE_POLICY_MANAGE}
    http_method_names = ["get", "post", "head"]

    @property
    def permission_scope(self):
        return FACILITY if getattr(self, "action", None) == "list" else ORGANIZATION

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generating the API file: no database
            return LeaveBalanceAdjustment.objects.none()
        return limit_to_visible(
            LeaveBalanceAdjustment.objects.select_related("created_by"),
            self.request.user,
            P.LEAVE_APPROVE,
            staff_field="staff_id",
        )

    @extend_schema(parameters=[OpenApiParameter("person", str, description="Staff member id")])
    def list(self, request, *args, **kwargs):
        rows = self.get_queryset()
        if request.query_params.get("person"):
            rows = rows.filter(staff_id=_uuid(request.query_params["person"], "person"))
        return Response(LeaveAdjustmentSerializer(rows[:200], many=True).data)

    @extend_schema(
        request=LeaveAdjustmentCreateSerializer, responses={201: LeaveAdjustmentSerializer}
    )
    @idempotent("leave_adjustments.create")
    def create(self, request):
        serializer = LeaveAdjustmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        row = balances.adjust_balance(
            actor=request.user, staff=_staff(data.pop("staff")), request=request, **data
        )
        return Response(LeaveAdjustmentSerializer(row).data, status=status.HTTP_201_CREATED)
