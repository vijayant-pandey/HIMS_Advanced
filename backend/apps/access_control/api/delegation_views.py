"""Cover arrangements / delegated access API (spec 4.4; HIMS-IAM-017).

Seeing arrangements needs ``access.roles.view``; arranging or ending cover needs
``access.role_assignments.manage`` (it gives access, so the same permission and the same
two-factor rule as giving access by hand). Everyone can see the arrangements they are part of.
"""

from datetime import timedelta
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db.models import Prefetch, Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.idempotency.decorators import idempotent

from .. import delegations
from ..catalog import P
from ..models import AccessDelegation, RoleAssignment
from ..reviews import scope_label
from .serializers import (
    AccessDelegationCreatedSerializer,
    AccessDelegationCreateSerializer,
    AccessDelegationEndSerializer,
    AccessDelegationSerializer,
    DelegableAccessSerializer,
)

# Most arrangements one list returns (newest first); narrow with the filters for older ones.
LIST_LIMIT = 200


def _person_id(value: str, field: str) -> UUID:
    """A mistyped id gives a clear 400, never a server error."""
    try:
        return UUID(value)
    except ValueError as exc:
        raise serializers.ValidationError({field: "Not a valid person id."}) from exc


def delegation_queryset():
    return AccessDelegation.objects.select_related(
        "delegator", "delegate", "created_by", "ended_by"
    ).prefetch_related(
        Prefetch(
            "assignments",
            queryset=RoleAssignment.objects.select_related(
                "role", "facility", "department"
            ).order_by("role__name"),
        )
    )


class AccessDelegationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = AccessDelegationSerializer
    pagination_class = None
    required_permissions = {
        "list": P.ROLES_VIEW,
        "retrieve": P.ROLES_VIEW,
        "create": P.ROLE_ASSIGNMENTS_MANAGE,
        "end": P.ROLE_ASSIGNMENTS_MANAGE,
        "delegable": P.ROLE_ASSIGNMENTS_MANAGE,
    }

    def get_queryset(self):
        return delegation_queryset().order_by("-starts_at")

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "status",
                str,
                enum=["current", "past", "all"],
                description="current (default) = active or starting later; past = finished or "
                "ended early.",
            ),
            OpenApiParameter("person", str, description="Only cover this person gives or gets."),
        ]
    )
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        now = timezone.now()
        open_filter = Q(ended_at__isnull=True, ends_at__gt=now)
        wanted = request.query_params.get("status", "current")
        if wanted == "current":
            queryset = queryset.filter(open_filter)
        elif wanted == "past":
            queryset = queryset.exclude(open_filter)
        elif wanted != "all":
            raise serializers.ValidationError({"status": "Use current, past or all."})
        person = request.query_params.get("person")
        if person:
            person = _person_id(person, "person")
            queryset = queryset.filter(Q(delegator_id=person) | Q(delegate_id=person))
        return Response(AccessDelegationSerializer(queryset[:LIST_LIMIT], many=True).data)

    @extend_schema(
        request=AccessDelegationCreateSerializer,
        responses={201: AccessDelegationCreatedSerializer},
    )
    @idempotent("access_delegations.create")
    def create(self, request):
        serializer = AccessDelegationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        delegation, skipped = delegations.create_delegation(
            actor=request.user,
            delegator=data["delegator"],
            delegate=data["delegate"],
            starts_at=data["starts_at"],
            ends_at=data["ends_at"],
            reason=data["reason"],
            assignment_ids=data["assignments"],
            request=request,
        )
        delegation = delegation_queryset().get(pk=delegation.pk)
        delegation.skipped = skipped
        return Response(
            AccessDelegationCreatedSerializer(delegation).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(request=AccessDelegationEndSerializer, responses=AccessDelegationSerializer)
    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        """End the cover now; every lent role is removed at once."""
        delegation = self.get_object()
        serializer = AccessDelegationEndSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delegations.end_delegation(
            actor=request.user,
            delegation_id=delegation.pk,
            version=serializer.validated_data["version"],
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(AccessDelegationSerializer(delegation_queryset().get(pk=pk)).data)

    @extend_schema(
        parameters=[OpenApiParameter("user", str, required=True)],
        responses=DelegableAccessSerializer(many=True),
    )
    @action(detail=False, methods=["get"])
    def delegable(self, request):
        """The person's own current access, and whether each can be lent."""
        user = (
            get_user_model()
            .objects.filter(pk=_person_id(request.query_params.get("user", ""), "user"))
            .first()
        )
        if user is None:
            raise serializers.ValidationError({"user": "No such person."})
        lendable, refused = delegations.delegable_assignments(user)
        rows = [(a, "") for a in lendable] + list(refused)
        rows.sort(key=lambda row: row[0].role.name)
        data = [
            {
                "id": a.pk,
                "role_name": a.role.name,
                "scope": scope_label(a),
                "valid_until": a.valid_until,
                "can_lend": not why,
                "why_not": why,
            }
            for a, why in rows
        ]
        return Response(DelegableAccessSerializer(data, many=True).data)


class MyDelegationsView(APIView):
    """Cover arrangements the signed-in person is part of (covering or covered): current ones
    and those that ended in the last 90 days."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: AccessDelegationSerializer(many=True)})
    def get(self, request):
        since = timezone.now() - timedelta(days=90)
        rows = (
            delegation_queryset()
            .filter(Q(delegator=request.user) | Q(delegate=request.user))
            .filter(Q(ended_at__isnull=True, ends_at__gt=since) | Q(ended_at__gt=since))
            .order_by("-starts_at")[:LIST_LIMIT]
        )
        return Response(AccessDelegationSerializer(rows, many=True).data)
