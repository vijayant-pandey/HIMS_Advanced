"""Record every request the supplier makes during support access (HIMS-IAM-021; spec 7.4
"establish a documented process for emergency support access and audit it").

While ``User.support_access_until`` is in the future, each request the account makes (screens,
API, admin console) is added to the audit log with its method, address and answer. The address
is recorded without its query string, so search words never reach the log. Background refreshes
(``X-HIMS-Background: 1``) are not clicks and are not recorded. Costs no query for anyone else:
the flag is read from the signed-in user already loaded for the request.
"""

from apps.identity.session_limits import is_background

from .support import is_supplier_on_support

SKIPPED_METHODS = frozenset({"HEAD", "OPTIONS"})


class SupportAccessAuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Read before the view runs: signing out ends the session, but the click still counts.
        user = getattr(request, "user", None)
        watched = (
            user is not None
            and user.is_authenticated
            and request.method not in SKIPPED_METHODS
            and not is_background(request)
            and is_supplier_on_support(user)
        )
        response = self.get_response(request)
        if watched:
            from apps.audit.services import AuditAction, record_audit_event

            record_audit_event(
                action=AuditAction.SUPPORT_ACCESS_USED,
                resource_type="request",
                resource_id=request.path[:64],  # the full address is in metadata
                actor=user,
                request=request,
                metadata={
                    "method": request.method,
                    "path": request.path[:500],
                    "status": response.status_code,
                },
            )
        return response
