"""Database access tab on the Compliance page (spec 13.2, 17.2, 30.5; HIMS-OPS-007).

Shows, from the database itself, that the app runs with its own limited user: it cannot change
the schema or the audit log, the read-only user cannot read credentials, and the break-glass
user is switched off. Read-only: users and rights are changed only with the setup command run by
the owner, never from the app (the app must not be able to raise its own rights).
"""

from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.catalog import P
from common import database_roles
from common.environment import LOCAL_ENVIRONMENTS


class DatabaseCheckSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    passed = serializers.BooleanField()
    detail = serializers.CharField(allow_blank=True)


class DatabaseAccessSerializer(serializers.Serializer):
    separated = serializers.BooleanField(help_text="Every check passed.")
    set_up = serializers.BooleanField(help_text="The app's own database user exists.")
    developer_pc = serializers.BooleanField(
        help_text="On a developer PC not setting it up is allowed; hosted, it must pass."
    )
    connected_as = serializers.CharField()
    app_user = serializers.CharField()
    readonly_user = serializers.CharField()
    breakglass_user = serializers.CharField()
    checks = DatabaseCheckSerializer(many=True)


class DatabaseAccessView(APIView):
    required_permissions = {"get": P.COMPLIANCE_VIEW}

    @extend_schema(responses=DatabaseAccessSerializer)
    def get(self, request):
        with connection.cursor() as cursor:
            result = database_roles.inspect(cursor)
        names = result["names"]
        checks = result["checks"]
        return Response(
            DatabaseAccessSerializer(
                {
                    "separated": result["set_up"] and all(c["passed"] for c in checks),
                    "set_up": result["set_up"],
                    "developer_pc": settings.HIMS_ENVIRONMENT in LOCAL_ENVIRONMENTS,
                    "connected_as": result["current_user"],
                    "app_user": names.app,
                    "readonly_user": names.readonly,
                    "breakglass_user": names.breakglass,
                    "checks": checks,
                }
            ).data
        )
