"""Hosting readiness tab on the Compliance page (spec 17, 30, 31; HIMS-OPS-020): this server's
settings and database checked against what any host must give HIMS. Read-only."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.catalog import P

from .. import hosting


class HostingCheckSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    spec = serializers.CharField(help_text="Specification sections.")
    status = serializers.ChoiceField(
        choices=hosting.STATUSES,
        help_text="ok: met; fail: needed before going on the internet at all; warn: fine with "
        "synthetic test data, needed before real patient data.",
    )
    detail = serializers.CharField()
    fix = serializers.CharField(allow_blank=True)


class HostingReadinessSerializer(serializers.Serializer):
    environment = serializers.CharField()
    developer_pc = serializers.BooleanField()
    ready_to_host = serializers.BooleanField()
    ready_for_real_data = serializers.BooleanField()
    failing = serializers.IntegerField()
    before_real_data = serializers.IntegerField()
    checks = HostingCheckSerializer(many=True)


class HostingReadinessView(APIView):
    """What this server still needs before it can host HIMS, read from its own settings."""

    required_permissions = {"get": P.COMPLIANCE_VIEW}

    @extend_schema(responses=HostingReadinessSerializer)
    def get(self, request):
        return Response(HostingReadinessSerializer(hosting.readiness()).data)
