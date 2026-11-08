"""Evidence that backups can really be restored (spec 13.5, 17.3, 23, 27.1; HIMS-OPS-009).

Both tables are append-only (database trigger): they are the proof an auditor asks for, so
nobody may change or remove a row afterwards. The backup files themselves live outside the
database, in ``HIMS_BACKUP_DIR``.
"""

import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone


class _AppendOnly(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError(f"{self._meta.verbose_name} records cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError(f"{self._meta.verbose_name} records cannot be changed.")


class Backup(_AppendOnly):
    """One backup: the database (PostgreSQL custom-format dump) and the stored documents, taken
    from the same moment, with a manifest describing what they contain."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now)
    created_by_id = models.UUIDField(null=True, blank=True)
    name = models.CharField(
        max_length=80, unique=True, help_text="Folder name inside the backup folder."
    )
    database_name = models.CharField(max_length=63)
    environment = models.CharField(max_length=20)
    release = models.CharField(max_length=64, blank=True)
    dump_bytes = models.PositiveBigIntegerField()
    dump_sha256 = models.CharField(max_length=64)
    tables = models.PositiveIntegerField()
    rows = models.PositiveBigIntegerField()
    documents = models.PositiveIntegerField()
    documents_bytes = models.PositiveBigIntegerField()
    seconds = models.FloatField(help_text="How long the backup took.")
    manifest = models.JSONField(
        encoder=DjangoJSONEncoder,
        help_text="Row counts and fingerprints per table, migrations, constraints, triggers, "
        "audit chain head and document fingerprints. No record contents.",
    )

    class Meta:
        db_table = "recovery_backups"
        ordering = ["-created_at"]
        verbose_name = "backup"

    def __str__(self) -> str:
        return self.name


class RestoreDrill(_AppendOnly):
    """One restore drill: a backup restored into a new, separate database and folder, every
    check run against the copy, then the copy removed."""

    class Outcome(models.TextChoices):
        PASSED = "passed", "Passed: everything came back"
        FAILED = "failed", "Failed: see the checks"

    class Trigger(models.TextChoices):
        ON_DEMAND = "on_demand", "Started by a person"
        COMMAND = "command", "Started from the server command line"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    backup = models.ForeignKey(Backup, on_delete=models.PROTECT, related_name="drills")
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(default=timezone.now)
    trigger = models.CharField(max_length=16, choices=Trigger.choices)
    requested_by_id = models.UUIDField(null=True, blank=True)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    restore_seconds = models.FloatField(
        help_text="Time to restore the database and documents (evidence for the RTO)."
    )
    backup_age_minutes = models.PositiveIntegerField(
        help_text="How old the backup was when restored (what would be lost: evidence for the RPO)."
    )
    restored_database = models.CharField(max_length=63)
    checks = models.JSONField(default=list, encoder=DjangoJSONEncoder)
    problem_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "recovery_restore_drills"
        ordering = ["-finished_at"]
        verbose_name = "restore drill"
        indexes = [models.Index(fields=["finished_at"], name="restore_drill_finished_idx")]

    def __str__(self) -> str:
        return f"{self.get_outcome_display()} ({self.finished_at:%Y-%m-%d %H:%M})"
