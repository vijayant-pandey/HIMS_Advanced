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


class AuditChainEntry(models.Model):
    """One link of the tamper-evident chain over audit events (spec 13.4, HIMS-SEC-010).

    Each committed audit event is "sealed" shortly after it is written: its fingerprint
    (SHA-256 of all its fields) is linked to the previous link with a keyed hash (HMAC-SHA256,
    key kept outside the database). Changing, deleting or back-dating any sealed event, or any
    link, breaks the chain and is reported by the integrity check. Append-only like
    ``AuditEvent`` (database trigger, migration 0003).
    """

    sequence = models.BigIntegerField(primary_key=True)
    event = models.OneToOneField(
        AuditEvent, on_delete=models.PROTECT, related_name="chain_entry", db_column="event_id"
    )
    event_hash = models.CharField(max_length=64)
    previous_hash = models.CharField(max_length=64)
    entry_hash = models.CharField(max_length=64)
    key_id = models.CharField(max_length=32)
    sealed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "audit_chain_entries"
        ordering = ["sequence"]
        verbose_name = "audit chain link"
        verbose_name_plural = "audit chain links"

    def __str__(self) -> str:
        return f"#{self.sequence} {self.entry_hash[:12]}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Audit chain links are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Audit chain links are append-only.")


class AuditIntegrityCheck(models.Model):
    """Result of one run of the audit integrity check (HIMS-SEC-010). Written once, never
    changed (database trigger). The latest ``chain_head`` can be written down outside HIMS
    as an independent anchor."""

    class Outcome(models.TextChoices):
        PASSED = "passed", "Passed: nothing was changed"
        FAILED = "failed", "Problems found"

    class Trigger(models.TextChoices):
        SCHEDULED = "scheduled", "Daily automatic check"
        ON_DEMAND = "on_demand", "Started by a person"
        COMMAND = "command", "Started from the server command line"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(default=timezone.now)
    trigger = models.CharField(max_length=16, choices=Trigger.choices)
    requested_by_id = models.UUIDField(null=True, blank=True)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    events_sealed = models.PositiveIntegerField(
        default=0, help_text="Events sealed into the chain just before this check."
    )
    entries_checked = models.PositiveBigIntegerField(default=0)
    last_sequence = models.BigIntegerField(default=0)
    chain_head = models.CharField(max_length=64, blank=True)
    problem_count = models.PositiveIntegerField(default=0)
    problems = models.JSONField(default=list, blank=True, encoder=DjangoJSONEncoder)
    unsealed_overdue = models.PositiveIntegerField(
        default=0,
        help_text="Events older than the sealing window that are not in the chain "
        "(written outside the normal path, or with a back-dated time).",
    )

    class Meta:
        db_table = "audit_integrity_checks"
        ordering = ["-finished_at"]
        indexes = [models.Index(fields=["finished_at"], name="audit_check_finished_idx")]

    def __str__(self) -> str:
        return f"{self.get_outcome_display()} ({self.finished_at:%Y-%m-%d %H:%M})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Integrity check results cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Integrity check results cannot be changed.")
