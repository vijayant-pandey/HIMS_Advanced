import csv

from django.db.models import Count, Q
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.services import AuditAction, record_audit_event
from apps.organizations.selectors import get_deployment_organization
from common.idempotency.decorators import idempotent

from .. import reviews, services
from ..catalog import P
from ..models import AccessReview, Permission, Role, RoleAssignment
from .serializers import (
    AccessReviewCancelSerializer,
    AccessReviewCompleteSerializer,
    AccessReviewDecideSerializer,
    AccessReviewItemSerializer,
    AccessReviewScheduleSerializer,
    AccessReviewSerializer,
    AccessReviewStartSerializer,
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


def _cell(value) -> str:
    """Spreadsheet-safe text: a leading = + - @ would otherwise run as a formula."""
    text = "" if value is None else str(value)
    return f"'{text}" if text[:1] in ("=", "+", "-", "@") else text


def _iso(value) -> str:
    return value.isoformat() if value else ""


class AccessReviewViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Periodic access reviews (HIMS-IAM-012). Auditors can read and download them;
    reviewers (``access.reviews.manage``) run them. Nobody decides on their own access."""

    serializer_class = AccessReviewSerializer
    pagination_class = None
    required_permissions = {
        "list": P.ACCESS_REVIEWS_VIEW,
        "retrieve": P.ACCESS_REVIEWS_VIEW,
        "items": P.ACCESS_REVIEWS_VIEW,
        "export": P.ACCESS_REVIEWS_VIEW,
        "schedule": P.ACCESS_REVIEWS_VIEW,
        "create": P.ACCESS_REVIEWS_MANAGE,
        "decide": P.ACCESS_REVIEWS_MANAGE,
        "complete": P.ACCESS_REVIEWS_MANAGE,
        "cancel": P.ACCESS_REVIEWS_MANAGE,
    }

    def get_queryset(self):
        return AccessReview.objects.select_related("started_by", "completed_by")

    @extend_schema(request=AccessReviewStartSerializer, responses={201: AccessReviewSerializer})
    @idempotent("access_reviews.start")
    def create(self, request):
        serializer = AccessReviewStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = reviews.start_review(
            actor=request.user,
            organization=get_deployment_organization(),
            request=request,
            **serializer.validated_data,
        )
        return Response(AccessReviewSerializer(review).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        parameters=[
            OpenApiParameter("decision", str, description="pending, keep, remove or ended"),
            OpenApiParameter("search", str, description="Name, email, role or place"),
        ],
        responses=AccessReviewItemSerializer(many=True),
    )
    @action(detail=True, methods=["get"])
    def items(self, request, pk=None):
        """Everyone's access in this review (all rows; filter with decision / search)."""
        review = self.get_object()
        queryset = review.items.select_related("assignment", "decided_by")
        decision = request.query_params.get("decision")
        if decision:
            queryset = queryset.filter(decision=decision)
        term = (request.query_params.get("search") or "").strip()
        if term:
            queryset = queryset.filter(
                Q(person_name__icontains=term)
                | Q(person_email__icontains=term)
                | Q(role_name__icontains=term)
                | Q(scope__icontains=term)
            )
        return Response(
            AccessReviewItemSerializer(queryset, many=True, context={"request": request}).data
        )

    @extend_schema(
        request=AccessReviewDecideSerializer, responses=AccessReviewItemSerializer(many=True)
    )
    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        """Keep or remove access for one or more people. Removing ends the access at once."""
        review = self.get_object()
        serializer = AccessReviewDecideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = reviews.decide_items(
            actor=request.user,
            review_id=review.pk,
            item_ids=serializer.validated_data["items"],
            decision=serializer.validated_data["decision"],
            comment=serializer.validated_data["comment"],
            request=request,
        )
        return Response(
            AccessReviewItemSerializer(items, many=True, context={"request": request}).data
        )

    @extend_schema(request=AccessReviewCompleteSerializer, responses=AccessReviewSerializer)
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        review = self.get_object()
        serializer = AccessReviewCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = reviews.complete_review(
            actor=request.user, review_id=review.pk, request=request, **serializer.validated_data
        )
        return Response(AccessReviewSerializer(review).data)

    @extend_schema(request=AccessReviewCancelSerializer, responses=AccessReviewSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        review = self.get_object()
        serializer = AccessReviewCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = reviews.cancel_review(
            actor=request.user, review_id=review.pk, request=request, **serializer.validated_data
        )
        return Response(AccessReviewSerializer(review).data)

    @extend_schema(responses=AccessReviewScheduleSerializer)
    @action(detail=False, methods=["get"])
    def schedule(self, request):
        """When the next review is due, and whether the one in progress is overdue."""
        return Response(AccessReviewScheduleSerializer(reviews.schedule()).data)

    @extend_schema(
        responses={(200, "text/csv"): OpenApiResponse(OpenApiTypes.STR, description="CSV file")}
    )
    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        """Download the review with every decision as CSV (evidence for auditors)."""
        review = self.get_object()
        items = list(review.items.select_related("decided_by"))
        record_audit_event(
            action=AuditAction.ACCESS_REVIEW_EXPORTED,
            resource_type="access_review",
            resource_id=review.pk,
            request=request,
            metadata={"rows": len(items)},
        )
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="access-review-{review.created_at:%Y%m%d}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(
            [
                "Review",
                "Review status",
                "Person",
                "Email",
                "Account could sign in",
                "Last signed in (UTC)",
                "Role",
                "Where",
                "Access given (UTC)",
                "Access ends (UTC)",
                "Decision",
                "Decided by",
                "Decided at (UTC)",
                "Comment",
            ]
        )
        for item in items:
            writer.writerow(
                [
                    _cell(value)
                    for value in (
                        review.title,
                        review.get_status_display(),
                        item.person_name,
                        item.person_email,
                        "yes" if item.account_active else "no",
                        _iso(item.last_signed_in_at),
                        item.role_name,
                        item.scope,
                        _iso(item.granted_at),
                        _iso(item.access_ends_at),
                        item.get_decision_display(),
                        item.decided_by.display_name if item.decided_by else "",
                        _iso(item.decided_at),
                        item.comment,
                    )
                ]
            )
        return response
