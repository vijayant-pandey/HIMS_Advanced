import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone


class AuditEvent(models.Model):
    """Append-only record of a security- or clinically-relevant action (spec 4.25, 13.4).

    UPDATE and DELETE are rejected by a database trigger (migration 0002, ADR-013). Actor and
    resource references are stored as plain identifiers rather than foreign keys so that audit
    history survives independently of the records it describes.
    """

    class ActorType(models.TextChoices):
        USER = "user", "User"
        SYSTEM = "system", "System"
        ANONYMOUS = "anonymous", "Anonymous"

    class Outcome(models.TextChoices):
        SUCCESS = "success", "Success"
        DENIED = "denied", "Denied"
        FAILURE = "failure", "Failure"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(default=timezone.now)
    organization_id = models.UUIDField(null=True, blank=True)
    facility_id = models.UUIDField(null=True, blank=True)
    actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    actor_id = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=100)
    resource_type = models.CharField(max_length=100)
    resource_id = models.CharField(max_length=64, blank=True)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    reason = models.TextField(blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    changes = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    metadata = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)

    class Meta:
        db_table = "audit_events"
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["occurred_at"], name="audit_occurred_idx"),
            models.Index(fields=["actor_id", "occurred_at"], name="audit_actor_idx"),
            models.Index(
                fields=["resource_type", "resource_id", "occurred_at"], name="audit_resource_idx"
            ),
            models.Index(fields=["action", "occurred_at"], name="audit_action_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.resource_type}:{self.resource_id} ({self.outcome})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Audit events are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Audit events are append-only.")
