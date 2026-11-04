from celery import shared_task

from .incidents import send_deadline_alerts


@shared_task(name="notifications.incident_deadline_alerts")
def incident_deadline_alerts() -> int:
    """Hourly: warn the compliance team about incident notices that are nearly due or overdue."""
    return send_deadline_alerts()
