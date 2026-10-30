"""Seal new audit events into the tamper-evident chain now (HIMS-SEC-010).

The same job runs every minute through Celery beat. Use this where no scheduler is running
(e.g. on a developer PC). Safe to run any number of times.
"""

from django.core.management.base import BaseCommand

from apps.audit.integrity import seal_pending_events


class Command(BaseCommand):
    help = "Add audit events that are not yet sealed to the tamper-evident chain."

    def handle(self, *args, **options):
        sealed = seal_pending_events()
        self.stdout.write(self.style.SUCCESS(f"Sealed {sealed} event(s)."))
