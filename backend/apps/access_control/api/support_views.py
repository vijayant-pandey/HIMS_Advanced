"""Supplier support access API, the "locked box" (spec 7.2, 7.4; HIMS-IAM-021).

Two sides:

* ``/support-access/``: the hospital (``support.access.manage``) sees every request, approves or
  refuses waiting ones and ends running access early.
* ``/my-support-access/``: the supplier's support account (``support.access.request``) asks,
  sees its own requests, cancels a waiting one and ends its access when the work is done.

Asking and approving give access, so both need a recent "confirm it's you" (HIMS-IAM-007), as
giving access by hand does.
"""

from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.idempotency.decorators import idempotent

from .. import support
from ..catalog import P
from ..models import Role, SupportAccess
from .serializers import PersonSerializer

# Most requests one list returns (newest first).
LIST_LIMIT = 200


class SupportRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "code", "name", "description"]
        read_only_fields = fields


class SupportAccessSerializer(serializers.ModelSerializer):
    requested_by = PersonSerializer(read_only=True)
    role = SupportRoleSerializer(read_only=True)
    status = serializers.ChoiceField(choices=SupportAccess.Status.choices, read_only=True)
    status_label = serializers.SerializerMethodField()
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    decided_by_name = serializers.CharField(
        source="decided_by.display_name", read_only=True, default=None, allow_null=True
    )
    ended_by_name = serializers.CharField(
        source="ended_by.display_name", read_only=True, default=None, allow_null=True
    )

    def get_status_label(self, access) -> str:
        return SupportAccess.Status(access.status).label

    class Meta:
        model = SupportAccess
        fields = [
            "id",
            "requested_by",
            "role",
            "kind",
            "kind_label",
            "reason",
            "hours",
            "status",
            "status_label",
            "created_at",
            "decided_by_name",
            "decided_at",
            "decision_note",
            "starts_at",
            "ends_at",
            "ended_at",
            "ended_by_name",
            "end_reason",
            "version",
        ]
        read_only_fields = fields


class SupportAccessRequestSerializer(serializers.Serializer):
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all())
    reason = serializers.CharField(max_length=2000)
    hours = serializers.IntegerField(min_value=1, max_value=24, required=False)
    emergency = serializers.BooleanField(
        default=False,
        help_text="Open the access at once without waiting for the hospital (emergencies only).",
    )


class SupportAccessDecisionSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class SupportAccessEndSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=2000)


class SupportAccessCancelSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


class SupportAccessOptionsSerializer(serializers.Serializer):
    roles = SupportRoleSerializer(many=True)
    default_hours = serializers.IntegerField()
    max_hours = serializers.IntegerField()
    emergency_notice = serializers.BooleanField(
        help_text="Whether the hospital's administrators are emailed about emergency access."
    )


def support_queryset():
    return SupportAccess.objects.select_related("requested_by", "role", "decided_by", "ended_by")


def _filtered(queryset, wanted: str):
    current = Q(state=SupportAccess.State.WAITING) | Q(
        state=SupportAccess.State.GRANTED, ends_at__gt=timezone.now()
    )
    if wanted == "current":
        return queryset.filter(current)
    if wanted == "past":
        return queryset.exclude(current)
    if wanted != "all":
        raise serializers.ValidationError({"status": "Use current, past or all."})
    return queryset


STATUS_PARAMETER = OpenApiParameter(
    "status",
    str,
    enum=["current", "past", "all"],
    description="current (default) = waiting or running now; past = everything else.",
)


class SupportAccessViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """The hospital's side: every request from the software supplier, emergency ones included."""

    serializer_class = SupportAccessSerializer
    pagination_class = None
    sensitive_actions = ("approve",)
    required_permissions = {
        "list": P.SUPPORT_ACCESS_MANAGE,
        "retrieve": P.SUPPORT_ACCESS_MANAGE,
        "approve": P.SUPPORT_ACCESS_MANAGE,
        "refuse": P.SUPPORT_ACCESS_MANAGE,
        "end": P.SUPPORT_ACCESS_MANAGE,
    }

    def get_queryset(self):
        return support_queryset().order_by("-created_at")

    @extend_schema(parameters=[STATUS_PARAMETER])
    def list(self, request, *args, **kwargs):
        rows = _filtered(self.get_queryset(), request.query_params.get("status", "current"))
        return Response(SupportAccessSerializer(rows[:LIST_LIMIT], many=True).data)

    @extend_schema(request=SupportAccessDecisionSerializer, responses=SupportAccessSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Give the supplier the access it asked for, from now for the hours it asked."""
        access = self.get_object()
        serializer = SupportAccessDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        support.approve(
            actor=request.user,
            access_id=access.pk,
            version=serializer.validated_data["version"],
            note=serializer.validated_data["note"],
            request=request,
        )
        return Response(SupportAccessSerializer(support_queryset().get(pk=pk)).data)

    @extend_schema(request=SupportAccessDecisionSerializer, responses=SupportAccessSerializer)
    @action(detail=True, methods=["post"])
    def refuse(self, request, pk=None):
        """Refuse a waiting request, with the reason the supplier is told."""
        access = self.get_object()
        serializer = SupportAccessDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        support.refuse(
            actor=request.user,
            access_id=access.pk,
            version=serializer.validated_data["version"],
            note=serializer.validated_data["note"],
            request=request,
        )
        return Response(SupportAccessSerializer(support_queryset().get(pk=pk)).data)

    @extend_schema(request=SupportAccessEndSerializer, responses=SupportAccessSerializer)
    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        """End the supplier's running access now."""
        access = self.get_object()
        serializer = SupportAccessEndSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        support.end(
            actor=request.user,
            access_id=access.pk,
            version=serializer.validated_data["version"],
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(SupportAccessSerializer(support_queryset().get(pk=pk)).data)


class MySupportAccessViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The supplier's side: ask for access, see its own requests, cancel or end them."""

    serializer_class = SupportAccessSerializer
    pagination_class = None
    sensitive_actions = ("create",)
    required_permissions = {
        "list": P.SUPPORT_ACCESS_REQUEST,
        "create": P.SUPPORT_ACCESS_REQUEST,
        "options": P.SUPPORT_ACCESS_REQUEST,
        "cancel": P.SUPPORT_ACCESS_REQUEST,
        "end": P.SUPPORT_ACCESS_REQUEST,
    }

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SupportAccess.objects.none()
        return support_queryset().filter(requested_by=self.request.user).order_by("-created_at")

    @extend_schema(parameters=[STATUS_PARAMETER])
    def list(self, request, *args, **kwargs):
        rows = _filtered(self.get_queryset(), request.query_params.get("status", "all"))
        return Response(SupportAccessSerializer(rows[:LIST_LIMIT], many=True).data)

    @extend_schema(request=SupportAccessRequestSerializer, responses={201: SupportAccessSerializer})
    @idempotent("support_access.create")
    def create(self, request):
        """Ask for access (waits for the hospital), or open it at once in an emergency."""
        serializer = SupportAccessRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        access = support.request_access(
            actor=request.user,
            role=data["role"],
            reason=data["reason"],
            hours=data.get("hours"),
            emergency=data["emergency"],
            request=request,
        )
        return Response(
            SupportAccessSerializer(support_queryset().get(pk=access.pk)).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(responses=SupportAccessOptionsSerializer)
    @action(detail=False, methods=["get"])
    def options(self, request):
        """What can be asked for, and for how long."""
        return Response(
            SupportAccessOptionsSerializer(
                {
                    "roles": support.askable_roles(),
                    "default_hours": support.default_hours(),
                    "max_hours": support.max_hours(),
                    "emergency_notice": support.emergency_notice(),
                }
            ).data
        )

    @extend_schema(request=SupportAccessCancelSerializer, responses=SupportAccessSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Withdraw a request the hospital has not answered yet."""
        access = self.get_object()
        serializer = SupportAccessCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        support.cancel(
            actor=request.user,
            access_id=access.pk,
            version=serializer.validated_data["version"],
            request=request,
        )
        return Response(SupportAccessSerializer(support_queryset().get(pk=pk)).data)

    @extend_schema(request=SupportAccessEndSerializer, responses=SupportAccessSerializer)
    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        """End your own running access when the work is done."""
        access = self.get_object()
        serializer = SupportAccessEndSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        support.end(
            actor=request.user,
            access_id=access.pk,
            version=serializer.validated_data["version"],
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(SupportAccessSerializer(support_queryset().get(pk=pk)).data)
