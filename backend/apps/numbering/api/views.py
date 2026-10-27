"""Numbering schemes API (HIMS-ORG-003)."""

from django.core.exceptions import ValidationError
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.access_control.catalog import P
from apps.access_control.selectors import check_permission, get_permission_scope
from common.idempotency.decorators import idempotent
from common.permissions import FACILITY, filter_by_facility_scope

from .. import services
from ..models import IssuedNumber, NumberingScheme
from .serializers import (
    IssuedNumberSerializer,
    NumberingPreviewRequestSerializer,
    NumberingPreviewSerializer,
    NumberingSchemeCreateSerializer,
    NumberingSchemeSerializer,
    NumberingSchemeUpdateSerializer,
    SetNextNumberSerializer,
)

VIEW_ACTIONS = {"list", "retrieve", "preview"}


class NumberingSchemeViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Hospital-wide schemes (no facility) apply everywhere, so anyone with ``numbering.view``
    sees them. Changing them needs ``numbering.manage`` for the whole organization; a facility's
    own scheme needs it at that facility."""

    serializer_class = NumberingSchemeSerializer
    pagination_class = None  # at most a few per document type
    permission_scope = FACILITY
    required_permissions = {
        "list": P.NUMBERING_VIEW,
        "retrieve": P.NUMBERING_VIEW,
        "preview": P.NUMBERING_VIEW,
        "create": P.NUMBERING_MANAGE,
        "partial_update": P.NUMBERING_MANAGE,
        "next_number": P.NUMBERING_MANAGE,
    }
    http_method_names = ["get", "post", "patch", "head"]

    def get_queryset(self):
        queryset = NumberingScheme.objects.select_related("facility")
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        visible = get_permission_scope(self.request.user, P.NUMBERING_VIEW).visible_facility_ids()
        if visible is not None:
            queryset = queryset.filter(Q(facility__isnull=True) | Q(facility_id__in=visible))
        document_type = self.request.query_params.get("document_type")
        if document_type:
            queryset = queryset.filter(document_type=document_type)
        return queryset

    def get_permission_context(self, obj):
        return obj.facility_id, None

    def check_object_permissions(self, request, obj):
        if obj.facility_id is None and self.action in VIEW_ACTIONS:
            return  # hospital-wide rules are visible to every holder of numbering.view
        super().check_object_permissions(request, obj)

    @extend_schema(parameters=[OpenApiParameter("document_type", str)])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request=NumberingSchemeCreateSerializer, responses={201: NumberingSchemeSerializer}
    )
    @idempotent("numbering.schemes.create")
    def create(self, request):
        serializer = NumberingSchemeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        facility = serializer.validated_data.get("facility")
        check_permission(
            request.user, P.NUMBERING_MANAGE, facility_id=facility.pk if facility else None
        )
        scheme = services.create_scheme(
            actor=request.user, request=request, **serializer.validated_data
        )
        return Response(NumberingSchemeSerializer(scheme).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=NumberingSchemeUpdateSerializer, responses=NumberingSchemeSerializer)
    def partial_update(self, request, pk=None):
        scheme = self.get_object()
        serializer = NumberingSchemeUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        scheme = services.update_scheme(
            actor=request.user,
            scheme_id=scheme.pk,
            version=data.pop("version"),
            request=request,
            **data,
        )
        return Response(NumberingSchemeSerializer(scheme).data)

    @extend_schema(request=SetNextNumberSerializer, responses=NumberingSchemeSerializer)
    @action(detail=True, methods=["post"], url_path="next-number")
    @idempotent("numbering.schemes.next_number")
    def next_number(self, request, pk=None):
        scheme = self.get_object()
        serializer = SetNextNumberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        scheme = services.set_next_number(
            actor=request.user, scheme_id=scheme.pk, request=request, **serializer.validated_data
        )
        return Response(NumberingSchemeSerializer(scheme).data)

    @extend_schema(request=NumberingPreviewRequestSerializer, responses=NumberingPreviewSerializer)
    @action(detail=False, methods=["post"])
    def preview(self, request):
        """Try settings before saving: returns an example number and any problems."""
        serializer = NumberingPreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        scheme = NumberingScheme(**serializer.validated_data)
        errors: dict[str, list[str]] = {}
        try:
            scheme.clean_fields(exclude=["organization"])
            scheme.clean()
        except ValidationError as exc:
            errors = exc.message_dict
        return Response(
            NumberingPreviewSerializer(
                {
                    "example": services.example_number(scheme),
                    "longest": scheme.longest_example(),
                    "errors": errors,
                }
            ).data
        )


class IssuedNumberViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Register of numbers handed out (read-only)."""

    serializer_class = IssuedNumberSerializer
    permission_scope = FACILITY
    required_permissions = {"list": P.NUMBERING_VIEW}

    def get_queryset(self):
        queryset = filter_by_facility_scope(self, IssuedNumber.objects.select_related("issued_by"))
        for param, lookup in (("document_type", "document_type"), ("facility", "facility_id")):
            value = self.request.query_params.get(param)
            if value:
                queryset = queryset.filter(**{lookup: value})
        search = self.request.query_params.get("value")
        if search:
            queryset = queryset.filter(value__icontains=search)
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("document_type", str),
            OpenApiParameter("facility", str),
            OpenApiParameter("value", str, description="Part of the number"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
