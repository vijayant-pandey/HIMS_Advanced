from celery import shared_task

from .incidents import send_deadline_alerts


@shared_task(name="notifications.incident_deadline_alerts")
def incident_deadline_alerts() -> int:
    """Hourly: warn the compliance team about incident notices that are nearly due or overdue."""
    return send_deadline_alerts()


@shared_task(name="platform.retention_purge")
def retention_purge() -> int:
    """Daily: delete housekeeping records past the periods the hospital set, honouring legal
    holds (HIMS-COMP-006). Deletes nothing while no period is set."""
    from .models import RetentionPurgeRun
    from .retention import run_purge

    return run_purge(trigger=RetentionPurgeRun.Trigger.SCHEDULED).deleted_total
