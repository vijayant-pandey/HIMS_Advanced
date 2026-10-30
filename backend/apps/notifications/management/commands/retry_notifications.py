"""Send failed emails/SMS again now (HIMS-NOTIF-001). The same job runs every 5 minutes through
Celery beat; use this where no scheduler runs (e.g. a developer PC). Safe to repeat."""

from django.core.management.base import BaseCommand

from apps.notifications.services import retry_due


class Command(BaseCommand):
    help = "Retry failed emails and SMS whose waiting time has passed."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(f"Retried {retry_due()} message(s)."))
