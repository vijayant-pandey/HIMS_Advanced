from celery import shared_task
from django.utils import timezone

from .models import IdempotencyRecord


@shared_task(name="platform.purge_expired_idempotency_records")
def purge_expired_idempotency_records() -> int:
    deleted, _ = IdempotencyRecord.objects.filter(expires_at__lt=timezone.now()).delete()
    return deleted
