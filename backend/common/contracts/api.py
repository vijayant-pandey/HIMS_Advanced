"""``GET /api/v1/api-endpoints/``: every endpoint, who may call it and what it records
(spec 29.1, 29.9; HIMS-DOC-001). Read-only; shown on the Access page's API endpoints tab and in
the console. Needs ``access.roles.view``: it answers "what does each permission open?"."""

from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.catalog import P

from . import inventory, listing


class ApiEndpointSerializer(serializers.Serializer):
    method = serializers.CharField()
    path = serializers.CharField()
    area = serializers.CharField()
    area_label = serializers.CharField()
    summary = serializers.CharField(allow_blank=True)
    access = serializers.ChoiceField(
        choices=inventory.ACCESS_CHOICES,
        help_text="public: no sign-in; signed_in: any account; permission: the one named.",
    )
    permission = serializers.CharField(allow_blank=True)
    permission_label = serializers.CharField(allow_blank=True)
    roles = serializers.ListField(
        child=serializers.CharField(), help_text="System roles holding the permission."
    )
    scope = serializers.CharField(
        allow_blank=True,
        help_text="organization: the grant must cover the whole hospital; facility: a grant at "
        "one facility or department is enough.",
    )
    confirm_identity = serializers.BooleanField(help_text='Needs a recent "confirm it\'s you".')
    idempotency = serializers.CharField(
        allow_blank=True, help_text="Idempotency-Key: empty (not taken), optional or required."
    )
    audit_actions = serializers.ListField(child=serializers.CharField())
    requirements = serializers.ListField(child=serializers.CharField())


class ApiEndpointSummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    public = serializers.IntegerField()
    signed_in = serializers.IntegerField()
    permission = serializers.IntegerField()
    confirm_identity = serializers.IntegerField()
    idempotent = serializers.IntegerField()
    audited_writes = serializers.IntegerField()
    writes = serializers.IntegerField()


class ApiEndpointListSerializer(serializers.Serializer):
    summary = ApiEndpointSummarySerializer()
    endpoints = ApiEndpointSerializer(many=True)


class ApiEndpointsView(APIView):
    """Every API endpoint with its access rule, scope and audit events, read from the code."""

    required_permissions = {"get": P.ROLES_VIEW}

    @extend_schema(responses=ApiEndpointListSerializer)
    def get(self, request):
        rows = listing.endpoint_rows()
        return Response({"summary": listing.summary(rows), "endpoints": rows})


urlpatterns = [path("api-endpoints/", ApiEndpointsView.as_view(), name="api-endpoints")]
