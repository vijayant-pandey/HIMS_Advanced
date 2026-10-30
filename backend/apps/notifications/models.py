import uuid

from django.db import models
from django.utils import timezone


class Notification(models.Model):
    """One email or SMS sent by HIMS (spec 4.23; HIMS-NOTIF-001), with its delivery outcome.

    ``body`` is the copy people may read in the log: sign-in links and other secrets are
    replaced by ``[hidden]``. ``body_encrypted`` holds the real text only until it has been
    delivered (needed to retry); it is cleared after a successful send.
    """

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting to be sent"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed, will retry"
        GAVE_UP = "gave_up", "Failed, no more retries"
        SKIPPED = "skipped", "Not sent"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now)
    channel = models.CharField(max_length=8, choices=Channel.choices)
    category = models.CharField(
        max_length=40, help_text="What it is about, e.g. account, security, staff, access, audit."
    )
    template = models.CharField(
        max_length=80, help_text="Which message, e.g. identity.invitation (no personal data)."
    )
    recipients = models.JSONField(default=list, help_text="Email addresses or phone numbers.")
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField(help_text="Readable copy with sign-in links and secrets hidden.")
    body_encrypted = models.TextField(blank=True, help_text="Real text until delivered.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    skip_reason = models.CharField(max_length=200, blank=True)
    related_type = models.CharField(max_length=40, blank=True)
    related_id = models.CharField(max_length=64, blank=True)
    requested_by_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"], name="notification_retry_idx"),
            models.Index(fields=["created_at"], name="notification_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_channel_display()} {self.template} ({self.get_status_display()})"
