from celery import shared_task

from .services import retry_due


@shared_task(name="notifications.retry_failed")
def retry_failed() -> int:
    """Every 5 minutes: send failed emails/SMS again once their pause has passed."""
    return retry_due()
