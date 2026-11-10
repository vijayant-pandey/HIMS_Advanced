from celery import shared_task

from .staffing import send_staffing_gap_alerts as _send_alerts


@shared_task(name="notifications.staffing_gap_alerts")
def staffing_gap_alerts() -> int:
    """Daily: email planners about staffing gaps in the next 7 days (each gap once)."""
    return _send_alerts()
