"""Session limits that background refreshes cannot defeat (spec 13.1; HIMS-SEC-011 finding F-01).

Django's own idle timeout (``SESSION_COOKIE_AGE`` with ``SESSION_SAVE_EVERY_REQUEST``) is renewed
by every request, including the timed refreshes of the Bed board, Background jobs, Rota and
"confirm it's you" status. A screen left open on a ward PC therefore stayed signed in for ever.

This middleware keeps two times in the session and checks them on every request:

* **Idle:** the last request a person made. Requests the app marks as background refreshes
  (header ``X-HIMS-Background: 1``) do not count, so an unattended screen is signed out after
  ``HIMS_SESSION_IDLE_SECONDS`` (default 30 minutes) however often it refreshes itself.
* **Absolute:** when the person signed in. After ``HIMS_SESSION_MAX_SECONDS`` (default 12 hours)
  they sign in again, whatever they are doing.

A session that runs out is ended like any other (register entry closed as expired, audited) and
the request continues as signed out, so the API answers 401 and the app shows the sign-in page.
"""

from django.conf import settings
from django.contrib.auth import logout
from django.utils import timezone

SIGNED_IN_AT = "_hims_signed_in_at"
LAST_ACTIVE = "_hims_last_active"
BACKGROUND_HEADER = "X-HIMS-Background"
IDLE = "idle"
TIME_LIMIT = "time_limit"


def _now() -> float:
    return timezone.now().timestamp()


def start(request) -> None:
    """Called when someone signs in (app or console)."""
    now = _now()
    request.session[SIGNED_IN_AT] = now
    request.session[LAST_ACTIVE] = now


def is_background(request) -> bool:
    return request.headers.get(BACKGROUND_HEADER) == "1"


def expired_reason(session, now: float) -> str | None:
    signed_in_at = session.get(SIGNED_IN_AT)
    last_active = session.get(LAST_ACTIVE)
    if signed_in_at is not None and now - signed_in_at > settings.HIMS_SESSION_MAX_SECONDS:
        return TIME_LIMIT
    if last_active is not None and now - last_active > settings.SESSION_COOKIE_AGE:
        return IDLE
    return None


def _end(request, user, reason: str) -> None:
    from apps.audit.services import AuditAction, record_audit_event

    from .models import UserSession

    session_key = request.session.session_key
    if session_key:
        # Closed as expired before logout() would close it as an ordinary sign-out.
        UserSession.objects.filter(session_key=session_key, ended_at__isnull=True).update(
            ended_at=timezone.now(), end_reason=UserSession.EndReason.EXPIRED
        )
    record_audit_event(
        action=AuditAction.AUTH_SESSIONS_ENDED,
        resource_type="user",
        resource_id=user.pk,
        actor=user,
        request=request,
        metadata={"reason": f"expired_{reason}", "sessions_ended": 1},
    )
    logout(request)


class SessionLimitsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            now = _now()
            reason = expired_reason(request.session, now)
            if reason:
                _end(request, user, reason)
            else:
                # Sessions from before these limits existed start counting now.
                request.session.setdefault(SIGNED_IN_AT, now)
                if not is_background(request) or LAST_ACTIVE not in request.session:
                    request.session[LAST_ACTIVE] = now
        return self.get_response(request)
