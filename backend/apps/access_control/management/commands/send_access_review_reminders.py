"""Send access review reminders now (HIMS-IAM-012).

The same job runs daily through Celery beat. Use this where no scheduler is running (e.g. on a
developer PC) or to check by hand. Safe to run any number of times.
"""

from django.core.management.base import BaseCommand

from apps.access_control.reviews import send_access_review_reminders


class Command(BaseCommand):
    help = "Email reviewers when a periodic access review is due or the open one is overdue."

    def handle(self, *args, **options):
        sent = send_access_review_reminders()
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} reminder(s)."))
