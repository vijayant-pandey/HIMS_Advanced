"""Virus scanning and traces status (HIMS-SEC-013, HIMS-SEC-020): what protects uploads and
what traces keep, for the Compliance page."""

from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.catalog import P
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.staff.documents import scan_stored_documents
from apps.staff.models import ScanStatus, StaffDocument
from common import virus_scan
from common.environment import LOCAL_ENVIRONMENTS

BLOCKED_DAYS = 30


class DocumentCountsSerializer(serializers.Serializer):
    clean = serializers.IntegerField()
    not_scanned = serializers.IntegerField()
    infected = serializers.IntegerField()


class TracesSerializer(serializers.Serializer):
    exporter = serializers.CharField(help_text="none, console or otlp")
    sent_elsewhere = serializers.BooleanField()
    error_text_filtered = serializers.BooleanField()


class ScanningStatusSerializer(serializers.Serializer):
    scanner = serializers.CharField(help_text="clamd, test-file or none")
    label = serializers.CharField()
    protects = serializers.BooleanField()
    reachable = serializers.BooleanField(allow_null=True, help_text="Empty without a real scanner")
    developer_pc = serializers.BooleanField()
    documents = DocumentCountsSerializer()
    blocked_last_30_days = serializers.IntegerField()
    traces = TracesSerializer()


class ScanResultSerializer(serializers.Serializer):
    checked = serializers.IntegerField()
    clean = serializers.IntegerField()
    infected = serializers.IntegerField()
    not_checked = serializers.IntegerField(help_text="This scanner cannot really check them")
    missing = serializers.IntegerField()


def scanning_status() -> dict:
    counts = dict(
        StaffDocument.objects.values_list("scan_status").annotate(n=Count("pk")).order_by()
    )
    since = timezone.now() - timedelta(days=BLOCKED_DAYS)
    return {
        **virus_scan.status(),
        "developer_pc": settings.HIMS_ENVIRONMENT in LOCAL_ENVIRONMENTS,
        "documents": {status.value: counts.get(status.value, 0) for status in ScanStatus},
        "blocked_last_30_days": AuditEvent.objects.filter(
            action__in=[AuditAction.UPLOAD_BLOCKED, AuditAction.STAFF_DOCUMENT_VIRUS_FOUND],
            occurred_at__gte=since,
        ).count(),
        "traces": {
            "exporter": settings.HIMS_TRACING_EXPORTER,
            "sent_elsewhere": settings.HIMS_TRACING_EXPORTER == "otlp",
            "error_text_filtered": True,
        },
    }


class ScanningStatusView(APIView):
    required_permissions = {"get": P.COMPLIANCE_VIEW}

    @extend_schema(responses=ScanningStatusSerializer)
    def get(self, request):
        return Response(ScanningStatusSerializer(scanning_status()).data)


class ScanDocumentsView(APIView):
    """Check stored documents not yet checked (up to 200 a time). A virus found blocks the file."""

    required_permissions = {"post": P.COMPLIANCE_MANAGE}

    @extend_schema(request=None, responses=ScanResultSerializer)
    def post(self, request):
        counts = scan_stored_documents(actor=request.user, request=request)
        return Response(ScanResultSerializer(counts).data)
