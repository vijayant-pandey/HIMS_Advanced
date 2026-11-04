"""Browser protection API (spec 13; HIMS-SEC-012, HIMS-SEC-014).

Browsers post block reports here without signing in, so that one address is public, rate limited
and write-only. Reading them needs ``compliance.view``; marking them reviewed needs
``compliance.manage``.
"""

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.catalog import P
from common.client_ip import client_ip
from common.security_headers import policy_mode
from common.throttling import ScopedThrottle

from .. import browser_reports
from ..models import BrowserSecurityReport

LIST_LIMIT = 200


class _CspReportParser(JSONParser):
    media_type = "application/csp-report"


class BrowserReportReceiveView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [_CspReportParser, JSONParser]
    throttle_classes = [ScopedThrottle]
    throttle_scope = "browser_report"

    @extend_schema(
        request={"application/csp-report": OpenApiTypes.OBJECT},
        responses={204: None},
        description="Where browsers send reports of what they blocked. The same empty answer "
        "whether a report is used or ignored.",
    )
    def post(self, request):
        if len(request.body) <= browser_reports.MAX_REPORT_BYTES:
            browser_reports.record_report(request.data)
        return Response(status=status.HTTP_204_NO_CONTENT)


class BrowserSecurityReportSerializer(serializers.ModelSerializer):
    reviewed_by_name = serializers.CharField(
        source="reviewed_by.display_name", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = BrowserSecurityReport
        fields = [
            "id",
            "day",
            "directive",
            "blocked",
            "page_path",
            "occurrences",
            "last_seen_at",
            "reviewed_by_name",
            "reviewed_at",
            "review_note",
            "version",
        ]
        read_only_fields = fields


class BrowserReportReviewSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class BrowserSecurityReportViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = BrowserSecurityReportSerializer
    pagination_class = None
    required_permissions = {"list": P.COMPLIANCE_VIEW, "review": P.COMPLIANCE_MANAGE}

    def get_queryset(self):
        rows = BrowserSecurityReport.objects.select_related("reviewed_by")
        return rows if self.action != "list" else rows[:LIST_LIMIT]

    @extend_schema(request=BrowserReportReviewSerializer, responses=BrowserSecurityReportSerializer)
    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        serializer = BrowserReportReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = browser_reports.review_report(
            actor=request.user,
            report_id=self.get_object().pk,
            request=request,
            **serializer.validated_data,
        )
        return Response(BrowserSecurityReportSerializer(report).data)


class SecurityStatusSerializer(serializers.Serializer):
    policy_mode = serializers.ChoiceField(choices=["enforcing", "report_only"])
    proxies_configured = serializers.BooleanField()
    your_address = serializers.CharField(allow_null=True)
    reports_to_review = serializers.IntegerField()


class SecurityStatusView(APIView):
    required_permissions = {"get": P.COMPLIANCE_VIEW}

    @extend_schema(responses=SecurityStatusSerializer)
    def get(self, request):
        return Response(
            {
                "policy_mode": policy_mode(),
                "proxies_configured": bool(settings.HIMS_TRUSTED_PROXIES),
                "your_address": client_ip(request),
                "reports_to_review": BrowserSecurityReport.objects.filter(
                    reviewed_at__isnull=True
                ).count(),
            }
        )
