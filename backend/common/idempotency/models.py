from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from common.models import UUIDPrimaryKeyModel


class IdempotencyRecord(UUIDPrimaryKeyModel):
    """Stored outcome of a write request made with an ``Idempotency-Key`` (spec 29.3).

    Scoped to actor + operation + key. The record is written in the same transaction as the
    business change, so a stored outcome always corresponds to committed state.
    """

    key = models.CharField(max_length=255)
    actor_id = models.UUIDField()
    operation = models.CharField(max_length=100)
    request_fingerprint = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField()
    response_body = models.JSONField(null=True, encoder=DjangoJSONEncoder)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "idempotency_records"
        constraints = [
            models.UniqueConstraint(
                fields=["actor_id", "operation", "key"], name="idempotency_scope_unique"
            )
        ]
        indexes = [models.Index(fields=["expires_at"], name="idempotency_expiry_idx")]
