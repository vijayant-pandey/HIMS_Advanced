"""Performance screen (spec 18, 28.6; HIMS-DATA-002, HIMS-OPS-017).

Seeing the results needs ``platform.performance.view``. Running the index check now needs
``platform.performance.manage``: it only reads (EXPLAIN of the app's own SELECT queries), so it
is not a "confirm it's you" action, and one check runs at a time. Response times and the volume
check run from the server command line (see docs/workflows/performance-checks.md).
"""

from django.db.models import OuterRef, Subquery
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import mixins, serializers, viewsets
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.access_control.catalog import P

from ..models import PerformanceCheck
from ..services import performance_status, run_index_check

HISTORY_LIMIT = 100


class QueryResultSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    table = serializers.CharField()
    table_rows = serializers.IntegerField()
    expected_indexes = serializers.ListField(child=serializers.CharField())
    indexes_used = serializers.ListField(child=serializers.CharField())
    full_reads = serializers.ListField(child=serializers.CharField())
    ms = serializers.FloatField(help_text="Execution time of one run (EXPLAIN ANALYZE).")
    budget_ms = serializers.FloatField()
    rows = serializers.IntegerField(allow_null=True)
    passed = serializers.BooleanField()
    detail = serializers.CharField(allow_blank=True)


class ScreenResultSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    path = serializers.CharField()
    status = serializers.IntegerField(help_text="HTTP status of the calls (200 expected).")
    samples = serializers.IntegerField()
    p50_ms = serializers.FloatField()
    p95_ms = serializers.FloatField()
    max_ms = serializers.FloatField()
    queries = serializers.IntegerField(help_text="Database queries one call makes.")
    target_ms = serializers.FloatField(help_text="p95 target (spec 18).")
    passed = serializers.BooleanField()
    detail = serializers.CharField(allow_blank=True)


class PerformanceCheckSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    trigger_label = serializers.CharField(source="get_trigger_display", read_only=True)
    requested_by_name = serializers.CharField(
        source="person_name", read_only=True, allow_null=True, default=None
    )

    class Meta:
        model = PerformanceCheck
        fields = [
            "id",
            "kind",
            "kind_label",
            "started_at",
            "finished_at",
            "trigger",
            "trigger_label",
            "requested_by_name",
            "outcome",
            "database",
            "environment",
            "release",
            "dataset_rows",
            "problem_count",
            "summary",
        ]
        read_only_fields = fields


class PerformanceCheckDetailSerializer(PerformanceCheckSerializer):
    dataset = serializers.DictField(
        child=serializers.IntegerField(), read_only=True, help_text="Rows per main table."
    )
    query_results = serializers.SerializerMethodField()
    screen_results = serializers.SerializerMethodField()

    class Meta(PerformanceCheckSerializer.Meta):
        fields = [
            *PerformanceCheckSerializer.Meta.fields,
            "dataset",
            "query_results",
            "screen_results",
        ]
        read_only_fields = fields

    @extend_schema_field(QueryResultSerializer(many=True))
    def get_query_results(self, check) -> list:
        if check.kind != PerformanceCheck.Kind.INDEXES:
            return []
        return QueryResultSerializer(check.results, many=True).data

    @extend_schema_field(ScreenResultSerializer(many=True))
    def get_screen_results(self, check) -> list:
        if check.kind != PerformanceCheck.Kind.RESPONSE_TIMES:
            return []
        return ScreenResultSerializer(check.results, many=True).data


class PerformanceStatusSerializer(serializers.Serializer):
    can_measure_here = serializers.BooleanField(
        help_text="False in hosted environments: response times come from monitoring there."
    )
    page_target_ms = serializers.FloatField()
    search_target_ms = serializers.FloatField()
    last_index_check = PerformanceCheckSerializer(allow_null=True)
    last_response_times = PerformanceCheckSerializer(allow_null=True)
    last_volume_index_check = PerformanceCheckSerializer(allow_null=True)
    last_volume_response_times = PerformanceCheckSerializer(allow_null=True)


def checks():
    from apps.identity.models import User

    return PerformanceCheck.objects.annotate(
        person_name=Subquery(
            User.objects.filter(pk=OuterRef("requested_by_id")).values("display_name")[:1]
        )
    ).order_by("-finished_at")


class PerformanceCheckViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Index checks and response-time measurements, newest first."""

    serializer_class = PerformanceCheckSerializer
    pagination_class = None
    required_permissions = {
        "list": P.PERFORMANCE_VIEW,
        "retrieve": P.PERFORMANCE_VIEW,
        "status": P.PERFORMANCE_VIEW,
        "create": P.PERFORMANCE_MANAGE,
    }

    def get_queryset(self):
        return checks()

    def get_serializer_class(self):
        if self.action in ("retrieve", "create"):
            return PerformanceCheckDetailSerializer
        return PerformanceCheckSerializer

    def list(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_queryset()[:HISTORY_LIMIT], many=True).data)

    @extend_schema(request=None, responses={201: PerformanceCheckDetailSerializer})
    def create(self, request, *args, **kwargs):
        """Run the index check on this hospital's database now (reads only; a few seconds)."""
        check = run_index_check(
            trigger=PerformanceCheck.Trigger.ON_DEMAND, actor=request.user, request=request
        )
        data = PerformanceCheckDetailSerializer(self.get_queryset().get(pk=check.pk)).data
        return Response(data, status=http_status.HTTP_201_CREATED)

    @extend_schema(responses=PerformanceStatusSerializer)
    @action(detail=False, methods=["get"])
    def status(self, request):
        """The latest results of each kind, on this database and on the volume copy."""
        data = performance_status()
        for key, value in data.items():
            if isinstance(value, PerformanceCheck):
                data[key] = self.get_queryset().filter(pk=value.pk).first()
        return Response(PerformanceStatusSerializer(data).data)
