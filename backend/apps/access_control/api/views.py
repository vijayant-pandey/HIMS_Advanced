from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.organizations.selectors import get_deployment_organization
from common.idempotency.decorators import idempotent

from .. import services
from ..catalog import P
from ..models import Permission, Role, RoleAssignment
from .serializers import (
    PermissionSerializer,
    RevokeSerializer,
    RoleAssignmentCreateSerializer,
    RoleAssignmentSerializer,
    RoleCreateSerializer,
    RoleSerializer,
    RoleUpdateSerializer,
)


class PermissionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = PermissionSerializer
    queryset = Permission.objects.filter(is_active=True)
    pagination_class = None
    required_permissions = {"list": P.ROLES_VIEW}


class RoleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = RoleSerializer
    required_permissions = {
        "list": P.ROLES_VIEW,
        "retrieve": P.ROLES_VIEW,
        "create": P.ROLES_MANAGE,
        "partial_update": P.ROLES_MANAGE,
    }
    http_method_names = ["get", "post", "patch", "head"]

    def get_queryset(self):
        now = timezone.now()
        active = Q(assignments__revoked_at__isnull=True, assignments__valid_from__lte=now) & (
            Q(assignments__valid_until__isnull=True) | Q(assignments__valid_until__gt=now)
        )
        return (
            Role.objects.prefetch_related("permissions")
            .annotate(active_assignments=Count("assignments", filter=active, distinct=True))
            .order_by("name")
        )  # aggregation drops Meta.ordering; keep pages stable

    @extend_schema(request=RoleCreateSerializer, responses={201: RoleSerializer})
    @idempotent("roles.create")
    def create(self, request):
        serializer = RoleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = services.create_role(
            actor=request.user,
            organization=get_deployment_organization(),
            request=request,
            **serializer.validated_data,
        )
        return Response(RoleSerializer(role).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=RoleUpdateSerializer, responses=RoleSerializer)
    def partial_update(self, request, pk=None):
        role = self.get_object()
        serializer = RoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        services.update_role(
            actor=request.user,
            role_id=role.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(RoleSerializer(self.get_queryset().get(pk=role.pk)).data)


class RoleAssignmentViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Role grants. Granting is checked against the actor's own permissions at the target
    scope, so administrators cannot escalate privileges (services._require_grantable)."""

    serializer_class = RoleAssignmentSerializer
    required_permissions = {
        "list": P.ROLES_VIEW,
        "retrieve": P.ROLES_VIEW,
        "create": P.ROLE_ASSIGNMENTS_MANAGE,
        "revoke": P.ROLE_ASSIGNMENTS_MANAGE,
    }

    def get_queryset(self):
        queryset = RoleAssignment.objects.select_related(
            "role", "user", "facility", "department", "granted_by", "revoked_by"
        ).order_by("-created_at")
        user_id = self.request.query_params.get("user")
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        role_id = self.request.query_params.get("role")
        if role_id:
            queryset = queryset.filter(role_id=role_id)
        if self.request.query_params.get("active") == "true":
            now = timezone.now()
            queryset = queryset.filter(revoked_at__isnull=True, valid_from__lte=now).filter(
                Q(valid_until__isnull=True) | Q(valid_until__gt=now)
            )
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("user", str),
            OpenApiParameter("role", str),
            OpenApiParameter("active", str, description="'true' = current access only"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request=RoleAssignmentCreateSerializer, responses={201: RoleAssignmentSerializer}
    )
    @idempotent("role_assignments.create")
    def create(self, request):
        serializer = RoleAssignmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignment = services.assign_role(
            actor=request.user, request=request, **serializer.validated_data
        )
        return Response(RoleAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=RevokeSerializer, responses=RoleAssignmentSerializer)
    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        assignment = self.get_object()
        serializer = RevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignment = services.revoke_role_assignment(
            actor=request.user,
            assignment_id=assignment.pk,
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(RoleAssignmentSerializer(assignment).data)
