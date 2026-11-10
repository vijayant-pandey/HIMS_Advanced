"""Retention tab on the Compliance page (spec 4.25, 28.1 #5; HIMS-COMP-006).

Reading needs ``compliance.view``. Setting a period, placing or releasing a legal hold and running
the purge need ``compliance.manage`` and a recent "confirm it's you": each can lead to records
being deleted for good, or kept against the hospital's policy.
"""

from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.catalog import P
from apps.identity.models import User
from common.idempotency.decorators import idempotent

from .. import retention
from ..models import LegalHold, RetentionPurgeRun, RetentionRule

RUN_LIST_LIMIT = 50
HOLD_LIST_LIMIT = 200


class RetentionCategorySerializer(serializers.Serializer):
    category = serializers.CharField()
    label = serializers.CharField()
    table = serializers.CharField()
    what = serializers.CharField(help_text="Which rows go, in plain words.")
    minimum_days = serializers.IntegerField()
    keep_days = serializers.IntegerField(allow_null=True, help_text="Empty = kept for ever.")
    pending_keep_days = serializers.IntegerField(allow_null=True)
    pending_from = serializers.DateTimeField(allow_null=True)
    updated_by_name = serializers.CharField(allow_null=True)
    updated_at = serializers.DateTimeField()
    version = serializers.IntegerField()
    would_delete = serializers.IntegerField(help_text="Rows the purge would delete now.")
    held = serializers.IntegerField(help_text="Rows past the period kept by a legal hold.")
    skipped = serializers.CharField(help_text="Why nothing of this kind would be deleted.")


class RetentionRunKindSerializer(serializers.Serializer):
    """What one run did for one kind of record."""

    keep_days = serializers.IntegerField(allow_null=True)
    older_than = serializers.CharField(allow_null=True, help_text="The cut-off used.")
    skipped = serializers.CharField(help_text="Why nothing of this kind was deleted.")
    deleted = serializers.IntegerField()
    held = serializers.IntegerField(help_text="Past the period but kept by a legal hold.")
    more_left = serializers.BooleanField(help_text="The limit per run was reached.")
    period_applied_now = serializers.BooleanField(
        help_text="A shorter period took effect at the start of this run."
    )


class RetentionPurgeRunSerializer(serializers.ModelSerializer):
    trigger_label = serializers.CharField(source="get_trigger_display", read_only=True)
    details = serializers.DictField(child=RetentionRunKindSerializer(), read_only=True)
    run_by_name = serializers.CharField(
        source="run_by.display_name", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = RetentionPurgeRun
        fields = [
            "id",
            "started_at",
            "finished_at",
            "trigger",
            "trigger_label",
            "run_by_name",
            "deleted_total",
            "details",
        ]
        read_only_fields = fields


class RetentionStatusSerializer(serializers.Serializer):
    categories = RetentionCategorySerializer(many=True)
    active_holds = serializers.IntegerField()
    wait_days = serializers.IntegerField(help_text="Days a shorter period waits before it applies.")
    last_run = RetentionPurgeRunSerializer(allow_null=True)


def _status() -> dict:
    retention.sync_rules()
    rules = {
        rule.category: rule for rule in RetentionRule.objects.select_related("updated_by").all()
    }
    plans = retention.preview()
    categories = []
    for key, kind in retention.CATEGORIES.items():
        rule = rules[key]
        categories.append(
            {
                "category": key,
                "label": kind.label,
                "table": kind.table,
                "what": kind.what,
                "minimum_days": kind.minimum_days,
                "keep_days": rule.keep_days,
                "pending_keep_days": rule.pending_keep_days,
                "pending_from": rule.pending_from,
                "updated_by_name": rule.updated_by.display_name if rule.updated_by else None,
                "updated_at": rule.updated_at,
                "version": rule.version,
                "would_delete": plans[key]["would_delete"],
                "held": plans[key]["held"],
                "skipped": plans[key]["skipped"],
            }
        )
    return {
        "categories": categories,
        "active_holds": LegalHold.objects.filter(released_at__isnull=True).count(),
        "wait_days": retention.SHORTER_PERIOD_WAIT.days,
        "last_run": RetentionPurgeRun.objects.select_related("run_by").first(),
    }


class RetentionView(APIView):
    required_permissions = {"get": P.COMPLIANCE_VIEW}

    @extend_schema(operation_id="retention_status", responses=RetentionStatusSerializer)
    def get(self, request):
        return Response(RetentionStatusSerializer(_status()).data)


class RetentionPeriodSerializer(serializers.Serializer):
    keep_days = serializers.IntegerField(
        min_value=1, allow_null=True, help_text="Days to keep; null = keep for ever."
    )
    version = serializers.IntegerField(min_value=1)


class RetentionPeriodView(APIView):
    """Set how long one kind of record is kept. A shorter period waits before it applies."""

    sensitive_actions = ("post",)
    required_permissions = {"post": P.COMPLIANCE_MANAGE}

    @extend_schema(
        operation_id="retention_period_set",
        request=RetentionPeriodSerializer,
        responses=RetentionStatusSerializer,
    )
    def post(self, request, category):
        if category not in retention.CATEGORIES:
            raise Http404
        serializer = RetentionPeriodSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        retention.set_period(
            actor=request.user, category=category, request=request, **serializer.validated_data
        )
        return Response(RetentionStatusSerializer(_status()).data)


class RetentionRunView(APIView):
    """Run the purge now instead of waiting for the daily job. Repeating it is harmless (the
    second run finds nothing new), so it is not wrapped in one idempotent transaction: deleting
    in small batches keeps the tables free for everyone else."""

    sensitive_actions = ("post",)
    required_permissions = {"post": P.COMPLIANCE_MANAGE}

    @extend_schema(
        operation_id="retention_run", request=None, responses={201: RetentionPurgeRunSerializer}
    )
    def post(self, request):
        run = retention.run_purge(
            trigger=RetentionPurgeRun.Trigger.MANUAL, actor=request.user, request=request
        )
        return Response(RetentionPurgeRunSerializer(run).data, status=status.HTTP_201_CREATED)


class RetentionPurgeRunViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The latest purge runs, newest first."""

    serializer_class = RetentionPurgeRunSerializer
    pagination_class = None
    required_permissions = {"list": P.COMPLIANCE_VIEW}

    def get_queryset(self):
        return RetentionPurgeRun.objects.select_related("run_by")[:RUN_LIST_LIMIT]


# --- Legal holds --------------------------------------------------------------------------------


class LegalHoldSerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(read_only=True)
    subject_name = serializers.CharField(
        source="subject_user.display_name", read_only=True, default=None, allow_null=True
    )
    subject_email = serializers.CharField(
        source="subject_user.email", read_only=True, default=None, allow_null=True
    )
    placed_by_name = serializers.CharField(
        source="placed_by.display_name", read_only=True, default=None, allow_null=True
    )
    released_by_name = serializers.CharField(
        source="released_by.display_name", read_only=True, default=None, allow_null=True
    )
    categories = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = LegalHold
        fields = [
            "id",
            "reference",
            "reason",
            "categories",
            "subject_name",
            "subject_email",
            "is_active",
            "placed_by_name",
            "placed_at",
            "released_by_name",
            "released_at",
            "release_reason",
            "version",
        ]
        read_only_fields = fields


class LegalHoldPlaceSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=120)
    reason = serializers.CharField(help_text="Why the records must be kept. No patient details.")
    categories = serializers.ListField(
        child=serializers.ChoiceField(choices=retention.CATEGORY_CHOICES),
        required=False,
        default=list,
        help_text="Kinds of record held; empty = every kind.",
    )
    subject_email = serializers.EmailField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Only records about this account; empty = everyone's.",
    )

    def validate_subject_email(self, value):
        if not value:
            return None
        user = User.objects.filter(email__iexact=value.strip()).first()
        if user is None:
            raise serializers.ValidationError("No account has this email.")
        return user


class LegalHoldReleaseSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(help_text="Why the records may now follow the normal periods.")


class LegalHoldViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = LegalHoldSerializer
    pagination_class = None
    sensitive_actions = ("create", "release")
    required_permissions = {
        "list": P.COMPLIANCE_VIEW,
        "create": P.COMPLIANCE_MANAGE,
        "release": P.COMPLIANCE_MANAGE,
    }

    def get_queryset(self):
        return LegalHold.objects.select_related(
            "subject_user", "placed_by", "released_by"
        ).order_by("released_at", "-placed_at")

    @extend_schema(
        parameters=[OpenApiParameter("active", str, description="'true' = not released yet")]
    )
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if request.query_params.get("active") == "true":
            queryset = queryset.filter(released_at__isnull=True)
        return Response(self.get_serializer(queryset[:HOLD_LIST_LIMIT], many=True).data)

    @extend_schema(request=LegalHoldPlaceSerializer, responses={201: LegalHoldSerializer})
    @idempotent("legal_holds.create")
    def create(self, request):
        serializer = LegalHoldPlaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        hold = retention.place_hold(
            actor=request.user,
            reference=data["reference"],
            reason=data["reason"],
            categories=data["categories"],
            subject_user=data["subject_email"],
            request=request,
        )
        return Response(
            LegalHoldSerializer(self.get_queryset().get(pk=hold.pk)).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=LegalHoldReleaseSerializer, responses=LegalHoldSerializer)
    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        serializer = LegalHoldReleaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        hold = retention.release_hold(
            actor=request.user,
            hold_id=self.get_object().pk,
            request=request,
            **serializer.validated_data,
        )
        return Response(LegalHoldSerializer(self.get_queryset().get(pk=hold.pk)).data)
