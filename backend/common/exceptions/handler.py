"""RFC 9457 Problem Details exception handler (spec 29.1, 29.2)."""

import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions as drf
from rest_framework.response import Response

from common.exceptions import DomainError, ScopeViolation
from common.request_context import get_request_id

logger = logging.getLogger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json"

_DRF_CODES = {
    drf.ParseError: ("MALFORMED_REQUEST", "Malformed request"),
    drf.NotAuthenticated: ("NOT_AUTHENTICATED", "Authentication required"),
    drf.AuthenticationFailed: ("NOT_AUTHENTICATED", "Authentication required"),
    drf.PermissionDenied: ("PERMISSION_DENIED", "Permission denied"),
    drf.NotFound: ("NOT_FOUND", "Not found"),
    drf.MethodNotAllowed: ("METHOD_NOT_ALLOWED", "Method not allowed"),
    drf.NotAcceptable: ("NOT_ACCEPTABLE", "Not acceptable"),
    drf.UnsupportedMediaType: ("UNSUPPORTED_MEDIA_TYPE", "Unsupported media type"),
    drf.Throttled: ("RATE_LIMITED", "Too many requests"),
}


def _problem(*, status: int, code: str, title: str, detail: str, **extra) -> Response:
    body = {
        "type": f"{settings.HIMS_PROBLEM_TYPE_BASE}{code.lower().replace('_', '-')}",
        "title": title,
        "status": status,
        "detail": detail,
        "code": code,
        "request_id": get_request_id(),
        **extra,
    }
    return Response(body, status=status, content_type=PROBLEM_CONTENT_TYPE)


def _flatten_validation_errors(detail, prefix: str = "") -> list[dict]:
    errors: list[dict] = []
    if isinstance(detail, dict):
        for key, value in detail.items():
            field = key if not prefix else f"{prefix}.{key}"
            if key == "non_field_errors":
                field = prefix or None
            errors.extend(_flatten_validation_errors(value, field or ""))
    elif isinstance(detail, list):
        for index, value in enumerate(detail):
            if isinstance(value, (dict, list)):
                errors.extend(_flatten_validation_errors(value, f"{prefix}[{index}]"))
            else:
                errors.extend(_flatten_validation_errors(value, prefix))
    else:
        errors.append(
            {
                "field": prefix or None,
                "message": str(detail),
                "code": getattr(detail, "code", "invalid"),
            }
        )
    return errors


def _audit_access_denied(context) -> None:
    """Record authorization denials (spec 4.25, 13.5).

    This runs after the view's transaction has rolled back, so the record survives.
    """
    request = context.get("request")
    if request is None or not getattr(request.user, "is_authenticated", False):
        return
    from apps.audit.models import AuditEvent
    from apps.audit.services import AuditAction, record_audit_event

    view = context.get("view")
    try:
        record_audit_event(
            action=AuditAction.ACCESS_DENIED,
            resource_type="api",
            resource_id=str(context.get("kwargs", {}).get("pk", ""))[:64],
            request=request,
            outcome=AuditEvent.Outcome.DENIED,
            metadata={
                "view": type(view).__name__ if view else None,
                "action": getattr(view, "action", None),
                "method": request.method,
            },
        )
    except Exception:
        logger.exception("Failed to record access-denied audit event")


def problem_details_exception_handler(exc, context):
    if isinstance(exc, (ScopeViolation, drf.PermissionDenied, DjangoPermissionDenied)):
        _audit_access_denied(context)

    if isinstance(exc, DomainError):
        return _problem(
            status=exc.status_code, code=exc.code, title=exc.title, detail=str(exc.detail)
        )

    if isinstance(exc, DjangoValidationError):
        exc = drf.ValidationError(
            exc.message_dict if hasattr(exc, "error_dict") else {"non_field_errors": exc.messages}
        )
    elif isinstance(exc, Http404):
        exc = drf.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = drf.PermissionDenied()

    if isinstance(exc, drf.ValidationError):
        return _problem(
            status=400,
            code="VALIDATION_ERROR",
            title="Validation failed",
            detail="One or more fields are invalid.",
            errors=_flatten_validation_errors(exc.detail),
        )

    if isinstance(exc, drf.APIException):
        code, title = next(
            (value for cls, value in _DRF_CODES.items() if isinstance(exc, cls)),
            ("ERROR", "Request failed"),
        )
        status = exc.status_code
        if isinstance(exc, (drf.NotAuthenticated, drf.AuthenticationFailed)):
            status = 401
        response = _problem(status=status, code=code, title=title, detail=str(exc.detail))
        if getattr(exc, "auth_header", None):
            response["WWW-Authenticate"] = exc.auth_header
        if getattr(exc, "wait", None):
            response["Retry-After"] = str(int(exc.wait))
        return response

    # Unexpected failure: log with the correlation ID; never leak internals to the caller.
    logger.exception("Unhandled API exception", extra={"view": type(context.get("view")).__name__})
    return _problem(
        status=500,
        code="INTERNAL_ERROR",
        title="Internal error",
        detail="An unexpected error occurred. Quote the request_id when contacting support.",
    )
