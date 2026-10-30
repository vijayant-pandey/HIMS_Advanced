"""Audit integrity screen for auditors (spec 13.4 tamper detection; HIMS-SEC-010).

Only ``audit.view`` holders can see the checks or start one (separation of duties: organization
administrators cannot). Starting a check is itself written to the audit log.
"""

from django.db.models import OuterRef, Subquery
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.access_control.catalog import P

from .. import catalog
from ..integrity import run_integrity_check
from ..models import AuditIntegrityCheck

# How many past checks the history shows (one runs every day).
HISTORY_LIMIT = 100


class IntegrityProblemSerializer(serializers.Serializer):
    """One problem. Which fields are present depends on the kind."""

    kind = serializers.CharField()
    text = serializers.CharField()
    sequence = serializers.IntegerField(required=False)
    last_missing = serializers.IntegerField(required=False)
    event_id = serializers.CharField(required=False)
    action = serializers.CharField(required=False)
    action_label = serializers.CharField(required=False)
    occurred_at = serializers.CharField(required=False)
    key_id = serializers.CharField(required=False)
    previous_last_sequence = serializers.IntegerField(required=False)
    last_sequence = serializers.IntegerField(required=False)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data.get("action"):
            data["action_label"] = catalog.label(data["action"])
        return data


class AuditIntegrityCheckSerializer(serializers.ModelSerializer):
    trigger_label = serializers.CharField(source="get_trigger_display", read_only=True)
    requested_by_name = serializers.CharField(read_only=True, allow_null=True, default=None)

    class Meta:
        model = AuditIntegrityCheck
        fields = [
            "id",
            "started_at",
            "finished_at",
            "trigger",
            "trigger_label",
            "requested_by_name",
            "outcome",
            "events_sealed",
            "entries_checked",
            "last_sequence",
            "chain_head",
            "problem_count",
            "unsealed_overdue",
        ]
        read_only_fields = fields


class AuditIntegrityCheckDetailSerializer(AuditIntegrityCheckSerializer):
    problems = IntegrityProblemSerializer(many=True, read_only=True)

    class Meta(AuditIntegrityCheckSerializer.Meta):
        fields = [*AuditIntegrityCheckSerializer.Meta.fields, "problems"]
        read_only_fields = fields


class AuditIntegrityStatusSerializer(serializers.Serializer):
    sealed_events = serializers.IntegerField(help_text="Events in the chain so far.")
    last_sealed_at = serializers.DateTimeField(allow_null=True)
    chain_head = serializers.CharField(help_text="Fingerprint of the newest link.")
    waiting_to_be_sealed = serializers.IntegerField(
        help_text="New events not sealed yet (normally sealed within a minute)."
    )
    key_id = serializers.CharField(help_text="Name of the key signing new links (never the key).")
    check_interval_hours = serializers.IntegerField()
    last_check = AuditIntegrityCheckSerializer(allow_null=True)


def with_requester(queryset):
    from apps.identity.models import User

    return queryset.annotate(
        requested_by_name=Subquery(
            User.objects.filter(pk=OuterRef("requested_by_id")).values("display_name")[:1]
        )
    )


class AuditIntegrityCheckViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Results of the tamper-evidence check, newest first, and "Check now"."""

    serializer_class = AuditIntegrityCheckSerializer
    pagination_class = None
    required_permissions = {
        "list": P.AUDIT_VIEW,
        "retrieve": P.AUDIT_VIEW,
        "create": P.AUDIT_VIEW,
        "status": P.AUDIT_VIEW,
    }

    def get_queryset(self):
        return with_requester(AuditIntegrityCheck.objects.all()).order_by("-finished_at")

    def get_serializer_class(self):
        if self.action in ("retrieve", "create"):
            return AuditIntegrityCheckDetailSerializer
        return AuditIntegrityCheckSerializer

    def list(self, request, *args, **kwargs):
        rows = self.get_queryset()[:HISTORY_LIMIT]
        return Response(self.get_serializer(rows, many=True).data)

    @extend_schema(request=None, responses={201: AuditIntegrityCheckDetailSerializer})
    def create(self, request, *args, **kwargs):
        """Seal new events and check the whole chain now. Takes a few seconds."""
        check = run_integrity_check(
            trigger=AuditIntegrityCheck.Trigger.ON_DEMAND, actor=request.user, request=request
        )
        check = self.get_queryset().get(pk=check.pk)
        return Response(
            AuditIntegrityCheckDetailSerializer(check).data, status=http_status.HTTP_201_CREATED
        )

    @extend_schema(responses=AuditIntegrityStatusSerializer)
    @action(detail=False, methods=["get"])
    def status(self, request):
        """Where the chain stands now, and the latest check."""
        from ..integrity import integrity_status

        data = integrity_status()
        last = data["last_check"]
        data["last_check"] = self.get_queryset().filter(pk=last.pk).first() if last else None
        data["check_interval_hours"] = 24
        return Response(AuditIntegrityStatusSerializer(data).data)
