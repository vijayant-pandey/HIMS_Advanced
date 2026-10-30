from celery import shared_task

from .integrity import run_integrity_check, seal_pending_events
from .models import AuditIntegrityCheck


@shared_task(name="platform.audit_seal_events")
def audit_seal_events() -> int:
    """Every minute: add newly written audit events to the tamper-evident chain."""
    return seal_pending_events()


# Walks the whole chain, so it may take longer than the default five-minute limit.
@shared_task(name="platform.audit_integrity_check", time_limit=3600, soft_time_limit=3540)
def audit_integrity_check() -> str:
    """Daily: check the whole chain; auditors are emailed if anything was changed."""
    return run_integrity_check(trigger=AuditIntegrityCheck.Trigger.SCHEDULED).outcome
