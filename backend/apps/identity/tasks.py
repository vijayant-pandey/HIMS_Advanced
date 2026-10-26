from celery import shared_task

from .sessions import clear_expired_sessions as _clear_expired_sessions


@shared_task(name="platform.clear_expired_sessions")
def clear_expired_sessions() -> int:
    return _clear_expired_sessions()
