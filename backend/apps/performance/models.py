"""Evidence that the database and the API stay fast enough (spec 18, 28.6; HIMS-DATA-002,
HIMS-OPS-017).

One table, append-only (database trigger): each row is one index check or one response-time
measurement with its numbers, kept like the restore drills so nobody can change a result
afterwards. No record contents are stored: only table names, index names, timings and counts.
"""

import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone


class PerformanceCheck(models.Model):
    class Kind(models.TextChoices):
        INDEXES = "indexes", "Index check (query plans)"
        RESPONSE_TIMES = "response_times", "Response times"

    class Outcome(models.TextChoices):
        PASSED = "passed", "Passed: every target met"
        FAILED = "failed", "Failed: see the results"

    class Trigger(models.TextChoices):
        ON_DEMAND = "on_demand", "Started by a person"
        COMMAND = "command", "Started from the server command line"
        VOLUME = "volume", "Volume check (throw-away copy with synthetic records)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(default=timezone.now)
    trigger = models.CharField(max_length=16, choices=Trigger.choices)
    requested_by_id = models.UUIDField(null=True, blank=True)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    database = models.CharField(
        max_length=63, help_text="The database measured (a volume check names its throw-away copy)."
    )
    environment = models.CharField(max_length=20)
    release = models.CharField(max_length=64, blank=True)
    dataset = models.JSONField(
        default=dict,
        encoder=DjangoJSONEncoder,
        help_text="Approximate rows per main table when measured. Counts only.",
    )
    dataset_rows = models.PositiveBigIntegerField(default=0)
    results = models.JSONField(
        default=list,
        encoder=DjangoJSONEncoder,
        help_text="One entry per query or screen: timings, index names, target, passed. "
        "No record contents.",
    )
    problem_count = models.PositiveIntegerField(default=0)
    summary = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "performance_checks"
        ordering = ["-finished_at"]
        verbose_name = "performance check"
        indexes = [
            models.Index(fields=["kind", "finished_at"], name="performance_check_kind_idx"),
        ]

    def __str__(self) -> str:
        when = f"{self.finished_at:%Y-%m-%d %H:%M}"
        return f"{self.get_kind_display()}: {self.get_outcome_display()} ({when})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Performance check records cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Performance check records cannot be changed.")
