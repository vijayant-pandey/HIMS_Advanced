"""``Idempotency-Key`` handling for DRF write endpoints (spec 29.3).

* Same key + same request  -> the stored response is replayed (``Idempotent-Replayed: true``).
* Same key + different body -> 409 ``IDEMPOTENCY_KEY_REUSED``.
* Concurrent duplicates     -> the second request blocks on the unique index until the first
  commits, then replays its outcome; if the first rolls back, the second proceeds normally.
* Error responses are not stored: the transaction rolls back and the client may retry.
"""

import functools
import hashlib
import json
import re
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.response import Response

from common.exceptions import ConflictError, DomainError

from .models import IdempotencyRecord

HEADER = "Idempotency-Key"
REPLAY_HEADER = "Idempotent-Replayed"
_VALID_KEY = re.compile(r"^[\x21-\x7e]{8,255}$")


class IdempotencyKeyRequired(DomainError):
    code = "IDEMPOTENCY_KEY_REQUIRED"
    title = "Idempotency key required"


class InvalidIdempotencyKey(DomainError):
    code = "INVALID_IDEMPOTENCY_KEY"
    title = "Invalid idempotency key"


def _fingerprint(request, view_kwargs) -> str:
    body = json.dumps(request.data, sort_keys=True, default=str, separators=(",", ":"))
    material = f"{request.method}|{request.path}|{sorted(view_kwargs.items())}|{body}"
    return hashlib.sha256(material.encode()).hexdigest()


def idempotent(operation: str, *, required: bool = False):
    def decorator(view_method):
        @functools.wraps(view_method)
        def wrapper(self, request, *args, **kwargs):
            key = request.headers.get(HEADER)
            if not key:
                if required:
                    raise IdempotencyKeyRequired(f"This operation requires an {HEADER} header.")
                return view_method(self, request, *args, **kwargs)
            if not _VALID_KEY.match(key):
                raise InvalidIdempotencyKey("Use 8-255 printable ASCII characters, e.g. a UUID.")

            fingerprint = _fingerprint(request, kwargs)
            with transaction.atomic():
                try:
                    with transaction.atomic():
                        record = IdempotencyRecord.objects.create(
                            key=key,
                            actor_id=request.user.pk,
                            operation=operation,
                            request_fingerprint=fingerprint,
                            response_status=0,
                            expires_at=timezone.now()
                            + timedelta(hours=settings.HIMS_IDEMPOTENCY_RETENTION_HOURS),
                        )
                except IntegrityError:
                    existing = IdempotencyRecord.objects.get(
                        actor_id=request.user.pk, operation=operation, key=key
                    )
                    if existing.request_fingerprint != fingerprint:
                        raise ConflictError(
                            "This idempotency key was already used with a different request.",
                            code="IDEMPOTENCY_KEY_REUSED",
                        ) from None
                    replay = Response(existing.response_body, status=existing.response_status)
                    replay[REPLAY_HEADER] = "true"
                    return replay

                response = view_method(self, request, *args, **kwargs)
                if response.status_code >= 400:
                    transaction.set_rollback(True)
                    return response
                record.response_status = response.status_code
                record.response_body = response.data
                record.save(update_fields=["response_status", "response_body"])
                return response

        return wrapper

    return decorator
