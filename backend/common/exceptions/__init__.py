"""Domain errors that map to RFC 9457 problem responses (spec 29.1, 29.2).

Services raise these; the API exception handler renders them. ``detail`` must be safe to show
to the caller: never include internal exception text, PHI or secrets.
"""


class DomainError(Exception):
    status_code = 400
    code = "DOMAIN_ERROR"
    title = "Request could not be completed"

    def __init__(self, detail: str | None = None, *, code: str | None = None):
        self.detail = detail or self.title
        if code:
            self.code = code
        super().__init__(self.detail)


class ConflictError(DomainError):
    status_code = 409
    code = "CONFLICT"
    title = "Conflict"


class StaleResourceError(ConflictError):
    code = "STALE_RESOURCE"
    title = "Resource was modified by someone else"


class InvalidStateTransition(ConflictError):
    code = "INVALID_STATE_TRANSITION"
    title = "Invalid state transition"


class NotFoundError(DomainError):
    status_code = 404
    code = "NOT_FOUND"
    title = "Not found"


class ScopeViolation(DomainError):
    status_code = 403
    code = "PERMISSION_DENIED"
    title = "Permission denied"
