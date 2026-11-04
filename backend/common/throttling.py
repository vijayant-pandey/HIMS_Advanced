"""Rate limits keyed on the real client address (spec 13.1; HIMS-SEC-014).

Out of the box, Django REST Framework keys anonymous limits on the whole X-Forwarded-For header,
which the sender controls: changing the header on each try would get around the sign-in limit.
"""

from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle

from .client_ip import client_ip


class _ClientIpMixin:
    def get_ident(self, request) -> str:
        return client_ip(request) or "unknown"


class AnonThrottle(_ClientIpMixin, AnonRateThrottle):
    pass


class UserThrottle(_ClientIpMixin, UserRateThrottle):
    pass


class ScopedThrottle(_ClientIpMixin, ScopedRateThrottle):
    pass
