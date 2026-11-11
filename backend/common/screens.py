"""The screens (the built React app) served by the same server as the API (spec 17, 31;
HIMS-OPS-022).

On a developer PC the screens come from Vite's dev server, as before. In a hosted image the built
app is in ``HIMS_FRONTEND_DIST`` and:

* WhiteNoise serves its files at the site root (``/assets/...`` are fingerprinted, so cached for a
  year; ``index.html`` is never cached), with the screens' own protection headers;
* every other screen address (``/staff``, ``/audit/integrity`` ...) answers with ``index.html``,
  so the app's own router shows the right page after a reload or from a bookmark;
* ``/api/``, ``/admin/``, ``/health/`` and ``/static/`` are never answered with the screens.

One site and one address for everything: the sign-in cookie and CSRF protection work exactly as on
a developer PC, where Vite forwards ``/api`` to Django.

The headers are those of ``frontend/security-headers.json`` (which ``vite preview`` sends); a test
keeps the two identical (HIMS-SEC-018: the screens' headers sent by the hosting).
"""

import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse

SCREENS_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
        "object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; "
        "report-uri /api/v1/security/browser-reports/"
    ),
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}
# Addresses the screens never answer: the server's own parts, and anything that looks like a file.
NOT_SCREENS = re.compile(r"^/(api|admin|health|static|assets|media-not-served)(/|$)|\.[^/]*$")
FINGERPRINTED = "/assets/"


def _page_headers() -> dict[str, str]:
    """For HTML pages. HSTS is left to Django's SecurityMiddleware, which sends it only over
    HTTPS; report-only mode is followed like everywhere else (HIMS_CSP_REPORT_ONLY)."""
    headers = {k: v for k, v in SCREENS_HEADERS.items() if k != "Strict-Transport-Security"}
    if settings.HIMS_CSP_REPORT_ONLY:
        headers["Content-Security-Policy-Report-Only"] = headers.pop("Content-Security-Policy")
    return headers


def add_headers(headers, path: str, url: str) -> None:
    """WhiteNoise hook (WHITENOISE_ADD_HEADERS_FUNCTION) for files of the built app. ``headers``
    is a ``wsgiref.headers.Headers``: setting a name replaces any earlier value."""
    if url.endswith(".html"):
        for name, value in _page_headers().items():
            headers[name] = value
        headers["Cache-Control"] = "no-cache"
    elif url.startswith(FINGERPRINTED):
        headers["Cache-Control"] = "public, max-age=31536000, immutable"


@lru_cache(maxsize=4)
def _index(folder: str) -> bytes:
    return (Path(folder) / "index.html").read_bytes()


def is_screen_path(path: str) -> bool:
    return not NOT_SCREENS.search(path)


def index(request, path: str = ""):
    """Any screen address: the app's start page; its router shows the page asked for."""
    folder = settings.HIMS_FRONTEND_DIST
    if not folder or not is_screen_path(request.path):
        raise Http404
    try:
        content = _index(folder)
    except OSError:
        raise Http404 from None
    response = HttpResponse(content, content_type="text/html; charset=utf-8")
    for name, value in _page_headers().items():
        response[name] = value
    response["Cache-Control"] = "no-cache"
    return response
