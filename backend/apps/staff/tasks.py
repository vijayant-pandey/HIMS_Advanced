from celery import shared_task

from .expiry import send_credential_expiry_alerts as _send_alerts


@shared_task(name="notifications.credential_expiry_alerts")
def credential_expiry_alerts() -> int:
    """Daily: email licence expiry alerts that are due (safe to run more than once)."""
    return _send_alerts()
