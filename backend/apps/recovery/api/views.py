"""Backups and restore drills screen (spec 13.5, 17.3, 23, 27.1; HIMS-OPS-009).

Seeing the evidence needs ``recovery.view`` (administrators and auditors). Making a backup or
running a drill needs ``recovery.manage``; a backup is a full copy of every record, so it also
needs a recent "confirm it's you" (HIMS-IAM-007). Both are written to the audit log.
"""

from django.db.models import OuterRef, Subquery
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.access_control.catalog import P

from ..models import Backup, RestoreDrill
from ..services import create_backup, recovery_status, run_restore_drill

# How many past backups and drills the screen lists.
HISTORY_LIMIT = 100


def _with_name(queryset, field: str):
    from apps.identity.models import User

    return queryset.annotate(
        person_name=Subquery(User.objects.filter(pk=OuterRef(field)).values("display_name")[:1])
    )


class BackupSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(
        source="person_name", read_only=True, allow_null=True, default=None
    )
    last_drill_outcome = serializers.CharField(read_only=True, allow_null=True, default=None)

    class Meta:
        model = Backup
        fields = [
            "id",
            "created_at",
            "created_by_name",
            "name",
            "environment",
            "release",
            "dump_bytes",
            "tables",
            "rows",
            "documents",
            "documents_bytes",
            "seconds",
            "last_drill_outcome",
        ]
        read_only_fields = fields


class DrillCheckSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    passed = serializers.BooleanField()
    detail = serializers.CharField(allow_blank=True)


class RestoreDrillSerializer(serializers.ModelSerializer):
    trigger_label = serializers.CharField(source="get_trigger_display", read_only=True)
    requested_by_name = serializers.CharField(
        source="person_name", read_only=True, allow_null=True, default=None
    )
    backup_name = serializers.CharField(source="backup.name", read_only=True)
    backup_created_at = serializers.DateTimeField(source="backup.created_at", read_only=True)

    class Meta:
        model = RestoreDrill
        fields = [
            "id",
            "started_at",
            "finished_at",
            "trigger",
            "trigger_label",
            "requested_by_name",
            "outcome",
            "backup",
            "backup_name",
            "backup_created_at",
            "restore_seconds",
            "backup_age_minutes",
            "problem_count",
        ]
        read_only_fields = fields


class RestoreDrillDetailSerializer(RestoreDrillSerializer):
    checks = DrillCheckSerializer(many=True, read_only=True)

    class Meta(RestoreDrillSerializer.Meta):
        fields = [*RestoreDrillSerializer.Meta.fields, "restored_database", "checks"]
        read_only_fields = fields


class StartDrillSerializer(serializers.Serializer):
    backup = serializers.UUIDField(help_text="The backup to restore and check.")


class RecoveryStatusSerializer(serializers.Serializer):
    can_run_here = serializers.BooleanField(
        help_text="False in hosted environments: there the cloud database service backs up."
    )
    backup_folder = serializers.CharField()
    tools = serializers.CharField(help_text="Where pg_dump/pg_restore were found ('' if not).")
    tools_problem = serializers.CharField(allow_blank=True)
    drill_interval_days = serializers.IntegerField()
    drill_overdue = serializers.BooleanField(
        help_text="No passed drill yet, or the last one is older than the interval."
    )
    last_backup = BackupSerializer(allow_null=True)
    last_drill = RestoreDrillSerializer(allow_null=True)
    last_passed_drill = RestoreDrillSerializer(allow_null=True)


def backups():
    latest = RestoreDrill.objects.filter(backup=OuterRef("pk")).order_by("-finished_at")
    return _with_name(Backup.objects.all(), "created_by_id").annotate(
        last_drill_outcome=Subquery(latest.values("outcome")[:1])
    )


def drills():
    return _with_name(RestoreDrill.objects.select_related("backup"), "requested_by_id").order_by(
        "-finished_at"
    )


class BackupViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Backups made on this computer, newest first, and "Make a backup now"."""

    serializer_class = BackupSerializer
    pagination_class = None
    required_permissions = {
        "list": P.RECOVERY_VIEW,
        "retrieve": P.RECOVERY_VIEW,
        "status": P.RECOVERY_VIEW,
        "create": P.RECOVERY_MANAGE,
    }
    sensitive_actions = ("create",)

    def get_queryset(self):
        return backups().order_by("-created_at")

    def list(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_queryset()[:HISTORY_LIMIT], many=True).data)

    @extend_schema(request=None, responses={201: BackupSerializer})
    def create(self, request, *args, **kwargs):
        """Back up the database and the documents now. Takes a few seconds on a developer PC."""
        backup = create_backup(actor=request.user, request=request)
        data = BackupSerializer(self.get_queryset().get(pk=backup.pk)).data
        return Response(data, status=http_status.HTTP_201_CREATED)

    @extend_schema(responses=RecoveryStatusSerializer)
    @action(detail=False, methods=["get"])
    def status(self, request):
        """The latest backup and restore drill, and whether a drill is overdue."""
        data = recovery_status()
        for key, queryset in (
            ("last_backup", self.get_queryset()),
            ("last_drill", drills()),
            ("last_passed_drill", drills()),
        ):
            row = data[key]
            data[key] = queryset.filter(pk=row.pk).first() if row else None
        return Response(RecoveryStatusSerializer(data).data)


class RestoreDrillViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Results of restore drills, newest first, and "Run a restore drill"."""

    serializer_class = RestoreDrillSerializer
    pagination_class = None
    required_permissions = {
        "list": P.RECOVERY_VIEW,
        "retrieve": P.RECOVERY_VIEW,
        "create": P.RECOVERY_MANAGE,
    }

    def get_queryset(self):
        return drills()

    def get_serializer_class(self):
        if self.action in ("retrieve", "create"):
            return RestoreDrillDetailSerializer
        return RestoreDrillSerializer

    def list(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_queryset()[:HISTORY_LIMIT], many=True).data)

    @extend_schema(request=StartDrillSerializer, responses={201: RestoreDrillDetailSerializer})
    def create(self, request, *args, **kwargs):
        """Restore a backup into a separate copy, check everything, then remove the copy.
        The live database and documents are not touched."""
        body = StartDrillSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        backup = get_object_or_404(Backup, pk=body.validated_data["backup"])
        drill = run_restore_drill(
            backup=backup,
            trigger=RestoreDrill.Trigger.ON_DEMAND,
            actor=request.user,
            request=request,
        )
        data = RestoreDrillDetailSerializer(self.get_queryset().get(pk=drill.pk)).data
        return Response(data, status=http_status.HTTP_201_CREATED)
