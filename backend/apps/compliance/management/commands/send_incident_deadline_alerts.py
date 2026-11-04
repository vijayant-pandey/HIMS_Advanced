"""Send incident deadline alerts now (HIMS-COMP-004). The same job runs hourly through Celery beat;
use this where no scheduler runs (e.g. a developer PC). Safe to repeat: each alert is sent once."""

from django.core.management.base import BaseCommand

from apps.compliance.incidents import send_deadline_alerts


class Command(BaseCommand):
    help = "Warn the compliance team about incident notices that are nearly due or overdue."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(f"Sent {send_deadline_alerts()} alert(s)."))
