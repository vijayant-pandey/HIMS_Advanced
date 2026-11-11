"""Background jobs screen (spec 14.3; HIMS-PLAT-014).

``platform.jobs.view`` sees how the outbox stands and the events that need a look;
``platform.jobs.manage`` sends a failed event again or dismisses it, always with a reason.
Event contents are not shown (they hold identifiers only; spec 29.7).
"""

from datetime import timedelta

from django.conf import settings
from django.db.models import OuterRef, Q, Subquery
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.access_control.catalog import P

from .maintenance import dismiss, outbox_health, send_again
from .models import OutboxEvent

LIST_LIMIT = 200

# What each event is for, in words (the raw name is shown too).
EVENT_LABELS = {
    "staff.member.created": "New member of staff (sends the account invitation)",
    "staff.member.employment_status_changed": "Staff employment status changed",
    "staff.credential.added": "Licence or qualification added",
    "bed.status.changed": "Bed status changed",
    "identity.invitation.issued": "Account invitation (sends the email)",
    "identity.password_reset.requested": "Password reset asked for (sends the email)",
    "identity.password.changed": "Password changed (sends the notice)",
}

SHOWS = {
    "attention": "Failed, or waiting too long",
    "failed": "Failed after every retry",
    "waiting": "Waiting",
    "dismissed": "Dismissed",
}


class OutboxEventSerializer(serializers.ModelSerializer):
    event_label = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    resolved_by_name = serializers.CharField(read_only=True, allow_null=True, default=None)

    class Meta:
        model = OutboxEvent
        fields = [
            "id",
            "event_type",
            "event_label",
            "occurred_at",
            "status",
            "status_label",
            "attempts",
            "available_at",
            "last_error",
            "aggregate_type",
            "aggregate_id",
            "resolved_at",
            "resolved_by_name",
            "resolution_note",
        ]
        read_only_fields = fields

    def get_event_label(self, event) -> str:
        return EVENT_LABELS.get(event.event_type, event.event_type)


class LastCleanupSerializer(serializers.Serializer):
    at = serializers.DateTimeField()
    events_deleted = serializers.IntegerField()
    markers_deleted = serializers.IntegerField()


class OutboxHealthSerializer(serializers.Serializer):
    waiting = serializers.IntegerField()
    oldest_waiting_minutes = serializers.IntegerField()
    retrying = serializers.IntegerField()
    stuck = serializers.IntegerField()
    failed = serializers.IntegerField()
    dismissed = serializers.IntegerField()
    published_last_24h = serializers.IntegerField()
    stuck_after_minutes = serializers.IntegerField()
    retention_days = serializers.IntegerField()
    max_attempts = serializers.IntegerField()
    last_cleanup = LastCleanupSerializer(allow_null=True)
    attention = serializers.ListField(child=serializers.CharField())


class ScheduledJobSerializer(serializers.Serializer):
    name = serializers.CharField()
    label = serializers.CharField()
    every_seconds = serializers.IntegerField()
    last_started_at = serializers.DateTimeField(allow_null=True)
    last_finished_at = serializers.DateTimeField(allow_null=True)
    last_outcome = serializers.CharField(
        allow_blank=True, help_text="running, ok or failed; empty when never run here."
    )
    last_duration_ms = serializers.IntegerField(allow_null=True)
    last_error = serializers.CharField(allow_blank=True)
    runs = serializers.IntegerField()
    failures = serializers.IntegerField()


class DecisionSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300, help_text="Why (kept in the audit log).")


def _events():
    from apps.identity.models import User

    return OutboxEvent.objects.annotate(
        resolved_by_name=Subquery(
            User.objects.filter(pk=OuterRef("resolved_by_id")).values("display_name")[:1]
        )
    )


class BackgroundJobViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Events that need a look, the outbox's health, and decisions on failed events."""

    serializer_class = OutboxEventSerializer
    pagination_class = None
    required_permissions = {
        "list": P.JOBS_VIEW,
        "health": P.JOBS_VIEW,
        "schedule": P.JOBS_VIEW,
        "send_again": P.JOBS_MANAGE,
        "dismiss": P.JOBS_MANAGE,
    }

    def get_queryset(self):
        return _events()

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "show", enum=list(SHOWS), description="Which events (default: attention)."
            )
        ]
    )
    def list(self, request, *args, **kwargs):
        show = request.query_params.get("show", "attention")
        Status = OutboxEvent.Status
        stuck_before = timezone.now() - timedelta(minutes=settings.HIMS_OUTBOX_STUCK_MINUTES)
        filters = {
            "attention": Q(status=Status.DEAD)
            | Q(status=Status.PENDING, occurred_at__lt=stuck_before),
            "failed": Q(status=Status.DEAD),
            "waiting": Q(status=Status.PENDING),
            "dismissed": Q(status=Status.DISMISSED),
        }
        rows = self.get_queryset().filter(filters.get(show, filters["attention"]))
        rows = rows.order_by("occurred_at")[:LIST_LIMIT]
        return Response(self.get_serializer(rows, many=True).data)

    @extend_schema(responses=OutboxHealthSerializer)
    @action(detail=False, methods=["get"])
    def health(self, request):
        """How many events wait, are retried or failed; the last clean-up."""
        return Response(OutboxHealthSerializer(outbox_health()).data)

    @extend_schema(responses=ScheduledJobSerializer(many=True))
    @action(detail=False, methods=["get"])
    def schedule(self, request):
        """The scheduled jobs and their last run, when run_scheduled_jobs starts them
        (HIMS-OPS-023). With Celery beat the runs are in the worker's log instead."""
        from .scheduler import board

        return Response(ScheduledJobSerializer(board(), many=True).data)

    def _decide(self, request, pk, decide):
        body = DecisionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        get_object_or_404(OutboxEvent, pk=pk)
        event = decide(
            actor=request.user,
            event_id=pk,
            reason=body.validated_data["reason"],
            request=request,
        )
        return Response(self.get_serializer(self.get_queryset().get(pk=event.pk)).data)

    @extend_schema(request=DecisionSerializer, responses=OutboxEventSerializer)
    @action(detail=True, methods=["post"], url_path="send-again")
    def send_again(self, request, pk=None):
        """Put a failed (or stuck) event back in the queue with a fresh set of retries."""
        return self._decide(request, pk, send_again)

    @extend_schema(request=DecisionSerializer, responses=OutboxEventSerializer)
    @action(detail=True, methods=["post"])
    def dismiss(self, request, pk=None):
        """Close a failed event that can never succeed; it is never retried."""
        return self._decide(request, pk, dismiss)
