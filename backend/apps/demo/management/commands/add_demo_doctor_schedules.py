"""Add the doctors' OPD sessions and exceptions (HIMS-OPD-001) to a demo hospital that was filled
before them, such as the hosted Development hospital (Render and Neon), which
``seed_demo_hospital`` refuses to fill twice.

Same safety rules as the seed: only demo deployments, or with ``--hosted-development`` only the
hosted Development environment (synthetic data only). Refused when the hospital already has a
doctor's session. One transaction: stopped half-way, nothing is kept.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.demo.opd import add_opd_examples
from apps.demo.seed import DemoError, check_safe
from apps.identity.accounts import active_administrators
from apps.scheduling.models import DoctorSchedule, ScheduleException


class Command(BaseCommand):
    help = "Add doctors' OPD sessions and exceptions to an already filled demo hospital."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hosted-development",
            action="store_true",
            help="The hosted Development hospital (synthetic data only), not a PC demo one",
        )

    def handle(self, *args, **opts):
        try:
            check_safe(hosted_development=opts["hosted_development"])
        except DemoError as exc:
            raise CommandError(str(exc)) from exc
        if DoctorSchedule.objects.exists():
            raise CommandError("This hospital already has doctors' OPD sessions: nothing added.")
        admin = active_administrators().order_by("date_joined").first()
        if admin is None:
            raise CommandError("Provision the hospital and fill the demo first.")
        with transaction.atomic():
            notes = add_opd_examples(actor=admin)
        sessions = DoctorSchedule.objects.count()
        if not sessions:
            raise CommandError("No doctors posted in outpatient departments: fill the demo first.")
        self.stdout.write(
            self.style.SUCCESS(
                f"Added {sessions} weekly OPD sessions and "
                f"{ScheduleException.objects.count()} exceptions:"
            )
        )
        for note in notes:
            self.stdout.write(f"  {note}")
        self.stdout.write(
            "See them on Doctor schedules: the head of department (hod.<branch>@), the branch "
            "administrator (admin.<branch>@) or the front desk (frontdesk.<branch>@)."
        )
