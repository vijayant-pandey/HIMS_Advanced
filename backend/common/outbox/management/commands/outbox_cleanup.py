"""Delete old published and dismissed outbox events now (HIMS-PLAT-014).

The same clean-up runs every day from the scheduler. Waiting and failed events are never
deleted. The result is written to the audit log.
"""

from django.core.management.base import BaseCommand

from common.outbox.maintenance import purge_old_events


class Command(BaseCommand):
    help = "Delete published and dismissed background events past the retention period."

    def handle(self, *args, **options):
        result = purge_old_events()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {result['events_deleted']} event(s) and {result['markers_deleted']} "
                f"duplicate-check marker(s) older than {result['retention_days']} days."
            )
        )
