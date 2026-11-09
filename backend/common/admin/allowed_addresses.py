"""The admin console answers only allowed addresses (spec 13.1, 13.4; HIMS-SEC-015, ADR-016).

Every console page, the sign-in page included, is checked against HIMS_ADMIN_ALLOWED_NETWORKS
using the real client address (common/client_ip.py). Anyone else gets the same "Not found"
page as when the console is switched off, so the console does not reveal that it exists. A
correct password, or a session stolen from someone allowed, does not help from elsewhere.

Each refused address is counted per day (apps/compliance/console_access.py); the first refusal
of the day, and the first one carrying a signed-in session, are written to the audit log.
A firewall or network rule in front of the server comes with hosting (HIMS-OPS-020).
"""

import logging

from django.conf import settings
from django.http import Http404
from django.views.defaults import page_not_found

from common.client_ip import client_ip, console_allows

logger = logging.getLogger(__name__)

CONSOLE_PATH = "/admin/"


def is_console_path(path: str) -> bool:
    return path.startswith(CONSOLE_PATH) or path == CONSOLE_PATH.rstrip("/")


class ConsoleAddressMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.HIMS_ENABLE_ADMIN and is_console_path(request.path_info):
            address = client_ip(request)
            if not console_allows(address):
                self._record(request, address)
                return page_not_found(request, Http404())
        return self.get_response(request)

    @staticmethod
    def _record(request, address) -> None:
        from apps.compliance.console_access import record_refusal

        try:
            record_refusal(request, address)
        except Exception:  # the refusal stands even when it cannot be counted
            logger.exception("console_refusal_not_recorded")
