"""Session register and "end all sessions" (HIMS-IAM-006; spec 4.4, 13.2, 13.5).

Two layers protect against a suspended or terminated person continuing to work:

1. Inactive accounts fail authentication on every request (Django's ModelBackend), and every
   permission check requires an active user (access_control.selectors).
2. This module deletes all of the person's sessions the moment the account is deactivated or the
   password changes, and records how many devices were signed out. Sessions created before this
   register existed are still stopped by layer 1.

Account deactivation is detected on the User model itself, so it works no matter how the account
was deactivated (staff termination, admin console, API, or future code paths).
"""

import logging
from importlib import import_module

from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models.signals import post_save, pre_save
from django.utils import timezone

from apps.audit.services import AuditAction, record_audit_event

from .models import User, UserSession

logger = logging.getLogger(__name__)


def _session_store_class():
    """The configured session engine, so ending sessions works for DB, cache or cached_db."""
    return import_module(settings.SESSION_ENGINE).SessionStore


def track_session(request, user) -> None:
    """Record the request's current session as belonging to ``user``."""
    session_key = getattr(getattr(request, "session", None), "session_key", None)
    if not session_key:
        return
    UserSession.objects.update_or_create(
        session_key=session_key,
        defaults={
            "user": user,
            "ip_address": request.META.get("REMOTE_ADDR") or None,
            "user_agent": request.headers.get("User-Agent", "")[:512],
            "ended_at": None,
            "end_reason": "",
        },
    )


def end_user_sessions(
    user: User,
    *,
    reason: str,
    actor=None,
    request=None,
    keep_session_key: str | None = None,
) -> int:
    """Delete every open session of ``user`` (optionally keeping the caller's own) and audit it.

    Returns the number of sessions ended.
    """
    open_sessions = UserSession.objects.filter(user=user, ended_at__isnull=True)
    if keep_session_key:
        open_sessions = open_sessions.exclude(session_key=keep_session_key)
    keys = list(open_sessions.values_list("session_key", flat=True))

    store = _session_store_class()
    for key in keys:
        store(session_key=key).delete()
    open_sessions.filter(session_key__in=keys).update(ended_at=timezone.now(), end_reason=reason)

    record_audit_event(
        action=AuditAction.AUTH_SESSIONS_ENDED,
        resource_type="user",
        resource_id=user.pk,
        actor=actor,
        request=request,
        metadata={"reason": reason, "sessions_ended": len(keys)},
    )
    return len(keys)


def clear_expired_sessions() -> int:
    """Remove expired sessions and close their register entries. Returns entries closed."""
    _session_store_class().clear_expired()
    if settings.SESSION_ENGINE != "django.contrib.sessions.backends.db":
        return 0
    from django.contrib.sessions.models import Session

    live_keys = Session.objects.values("session_key")
    return (
        UserSession.objects.filter(ended_at__isnull=True)
        .exclude(session_key__in=live_keys)
        .update(ended_at=timezone.now(), end_reason=UserSession.EndReason.EXPIRED)
    )


# --- Signal receivers (connected in IdentityConfig.ready) ---------------------------------


def on_user_logged_in(sender, request, user, **kwargs) -> None:
    track_session(request, user)


def on_user_logged_out(sender, request, user, **kwargs) -> None:
    session_key = getattr(getattr(request, "session", None), "session_key", None)
    if session_key:
        UserSession.objects.filter(session_key=session_key, ended_at__isnull=True).update(
            ended_at=timezone.now(), end_reason=UserSession.EndReason.LOGOUT
        )


def remember_previous_active_state(sender, instance: User, update_fields=None, **kwargs) -> None:
    if instance._state.adding or (update_fields is not None and "is_active" not in update_fields):
        instance._hims_was_active = None
        return
    instance._hims_was_active = (
        User.objects.filter(pk=instance.pk).values_list("is_active", flat=True).first()
    )


def end_sessions_when_deactivated(sender, instance: User, created=False, **kwargs) -> None:
    if not created and getattr(instance, "_hims_was_active", None) and not instance.is_active:
        ended = end_user_sessions(instance, reason=UserSession.EndReason.ACCOUNT_DEACTIVATED)
        logger.info(
            "Account deactivated; sessions ended",
            extra={"user_id": str(instance.pk), "sessions_ended": ended},
        )


def connect_signals() -> None:
    user_logged_in.connect(on_user_logged_in, dispatch_uid="hims.identity.track_login")
    user_logged_out.connect(on_user_logged_out, dispatch_uid="hims.identity.track_logout")
    pre_save.connect(
        remember_previous_active_state, sender=User, dispatch_uid="hims.identity.was_active"
    )
    post_save.connect(
        end_sessions_when_deactivated, sender=User, dispatch_uid="hims.identity.deactivated"
    )
