from celery import shared_task

from .opd_queue import mark_no_shows as _mark_no_shows


@shared_task(name="scheduling.mark_no_shows")
def mark_no_shows() -> int:
    """Every 15 minutes: booked patients not checked in when their session ended are marked "did
    not come" (D12; HIMS-OPD-003)."""
    return _mark_no_shows()
