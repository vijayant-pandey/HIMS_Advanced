"""Browser protection headers on every backend response (spec 13; HIMS-SEC-012).

Django already sends X-Content-Type-Options, Referrer-Policy, X-Frame-Options and
Cross-Origin-Opener-Policy, and HSTS in managed environments. This adds the rest. The screens are
served separately, with the policy in frontend/security-headers.json. See
docs/workflows/security-headers.md and ADR-022.
"""

from django.conf import settings

BROWSER_REPORT_PATH = "/api/v1/security/browser-reports/"

# JSON and file downloads: a browser should never run or load anything from these responses.
API_POLICY = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
# The admin console has no inline scripts; its stylesheets and templates do use inline styles.
CONSOLE_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
    f"frame-ancestors 'none'; base-uri 'self'; form-action 'self'; report-uri {BROWSER_REPORT_PATH}"
)
# Swagger UI loads from a CDN with an inline start-up script. It is off in managed environments
# unless HIMS_ENABLE_API_DOCS is set.
API_DOCS_POLICY = (
    "default-src 'none'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://cdn.jsdelivr.net; connect-src 'self'; frame-ancestors 'none'; "
    "base-uri 'none'; form-action 'none'"
)
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"


def policy_for(path: str) -> str:
    if path.startswith("/admin/"):
        return CONSOLE_POLICY
    if path.startswith("/api/docs/"):
        return API_DOCS_POLICY
    return API_POLICY


def policy_mode() -> str:
    return "report_only" if settings.HIMS_CSP_REPORT_ONLY else "enforcing"


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        header = (
            "Content-Security-Policy-Report-Only"
            if settings.HIMS_CSP_REPORT_ONLY
            else "Content-Security-Policy"
        )
        response.headers.setdefault(header, policy_for(request.path))
        response.headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        return response
