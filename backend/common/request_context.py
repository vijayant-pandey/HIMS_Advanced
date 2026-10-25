"""Request/correlation ID handling (spec 27.2, 29.1).

Every API request gets a correlation ID that is returned to the client, attached to logs,
audit events and outbox events, and propagated into Celery tasks.
"""

import contextvars
import logging
import re
import uuid

from django.conf import settings

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9\-]{8,64}$")
_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "hims_request_id", default=None
)


def new_request_id() -> str:
    return str(uuid.uuid4())


def get_request_id() -> str | None:
    return _request_id.get()


def set_request_id(value: str | None) -> contextvars.Token:
    return _request_id.set(value)


class RequestContextMiddleware:
    """Accepts a well-formed inbound X-Request-ID (e.g. from the ALB/SPA) or generates one."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        inbound = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = inbound if _VALID_REQUEST_ID.match(inbound) else new_request_id()
        request.request_id = request_id
        token = set_request_id(request_id)
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)
        response[REQUEST_ID_HEADER] = request_id
        return response


class RequestContextLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        record.deployment_id = getattr(settings, "HIMS_DEPLOYMENT_ID", "-")
        record.environment = getattr(settings, "HIMS_ENVIRONMENT", "-")
        record.release = getattr(settings, "HIMS_RELEASE", "-")
        return True
