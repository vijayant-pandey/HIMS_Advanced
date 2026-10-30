from celery import shared_task

from .reviews import send_access_review_reminders


@shared_task(name="notifications.access_review_reminders")
def access_review_reminders() -> int:
    """Daily: email reviewers when an access review is due or overdue (sent once each)."""
    return send_access_review_reminders()
