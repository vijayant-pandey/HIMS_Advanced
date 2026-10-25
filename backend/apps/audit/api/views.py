from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, viewsets

from apps.access_control.catalog import P

from ..models import AuditEvent
from ..services import AuditAction, record_audit_event

FILTERS = {
    "actor_id": "actor_id",
    "action": "action",
    "resource_type": "resource_type",
    "resource_id": "resource_id",
    "outcome": "outcome",
    "facility_id": "facility_id",
    "occurred_after": "occurred_at__gte",
    "occurred_before": "occurred_at__lt",
}


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "occurred_at",
            "facility_id",
            "actor_type",
            "actor_id",
            "action",
            "resource_type",
            "resource_id",
            "outcome",
            "reason",
            "request_id",
            "ip_address",
            "changes",
            "metadata",
        ]
        read_only_fields = fields


class AuditEventViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Audit search for auditors. Searching the audit log is itself audited."""

    serializer_class = AuditEventSerializer
    required_permissions = {"list": P.AUDIT_VIEW}

    def get_queryset(self):
        params = self.request.query_params
        lookups = {orm: params[name] for name, orm in FILTERS.items() if params.get(name)}
        return AuditEvent.objects.filter(**lookups).order_by("-occurred_at")

    @extend_schema(parameters=[OpenApiParameter(name, str) for name in FILTERS])
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        record_audit_event(
            action=AuditAction.AUDIT_SEARCHED,
            resource_type="audit_event",
            request=request,
            metadata={"filters": {k: v for k, v in request.query_params.items() if k in FILTERS}},
        )
        return response
