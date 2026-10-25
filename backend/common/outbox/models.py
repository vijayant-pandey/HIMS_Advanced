import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Q
from django.utils import timezone


class OutboxEvent(models.Model):
    """A domain event committed atomically with the change that caused it (spec 14.2, 29.7)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PUBLISHED = "published", "Published"
        DEAD = "dead", "Dead (retries exhausted)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=150)
    event_version = models.PositiveSmallIntegerField(default=1)
    occurred_at = models.DateTimeField(default=timezone.now)
    customer_id = models.CharField(max_length=64)
    facility_id = models.UUIDField(null=True, blank=True)
    aggregate_type = models.CharField(max_length=100)
    aggregate_id = models.CharField(max_length=64)
    correlation_id = models.CharField(max_length=64, blank=True)
    causation_id = models.CharField(max_length=64, blank=True)
    payload = models.JSONField(default=dict, encoder=DjangoJSONEncoder)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    published_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "outbox_events"
        indexes = [
            models.Index(
                fields=["available_at", "occurred_at"],
                condition=Q(status="pending"),
                name="outbox_pending_idx",
            ),
            models.Index(fields=["aggregate_type", "aggregate_id"], name="outbox_aggregate_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} {self.id} ({self.status})"

    def envelope(self) -> dict:
        return {
            "event_id": str(self.id),
            "event_type": self.event_type,
            "event_version": self.event_version,
            "occurred_at": self.occurred_at.isoformat(),
            "customer_id": self.customer_id,
            "facility_id": str(self.facility_id) if self.facility_id else None,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "payload": self.payload,
        }


class ProcessedEvent(models.Model):
    """Consumer-side deduplication: one row per (handler, event) processed (spec 29.7)."""

    handler = models.CharField(max_length=200)
    event_id = models.UUIDField()
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "outbox_processed_events"
        constraints = [
            models.UniqueConstraint(fields=["handler", "event_id"], name="processed_event_unique")
        ]

    def __str__(self) -> str:
        return f"{self.handler} processed {self.event_id}"
