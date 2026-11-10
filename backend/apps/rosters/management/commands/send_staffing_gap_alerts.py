"""Send staffing gap alerts now (HIMS-STAFF-015).

The same job runs daily through Celery beat. Use this where no scheduler is running (e.g. on a
developer PC) or to check alerts by hand. Safe to run any number of times.
"""

from django.core.management.base import BaseCommand

from apps.rosters.staffing import send_staffing_gap_alerts


class Command(BaseCommand):
    help = "Email planners about shifts below the hospital's minimum in the next 7 days."

    def handle(self, *args, **options):
        told = send_staffing_gap_alerts()
        self.stdout.write(self.style.SUCCESS(f"Told planners about {told} gap(s)."))
