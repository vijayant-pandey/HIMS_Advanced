"""Send licence expiry alerts now (HIMS-STAFF-006).

The same job runs daily through Celery beat. Use this where no scheduler is running (e.g. on a
developer PC) or to check alerts by hand. Safe to run any number of times.
"""

from django.core.management.base import BaseCommand

from apps.staff.expiry import send_credential_expiry_alerts


class Command(BaseCommand):
    help = "Email licence expiry alerts that are due (60/30/7 days before and once expired)."

    def handle(self, *args, **options):
        sent = send_credential_expiry_alerts()
        self.stdout.write(self.style.SUCCESS(f"Sent alerts for {sent} licence(s)."))
