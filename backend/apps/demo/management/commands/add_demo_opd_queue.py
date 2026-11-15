"""Add today's OPD queue (HIMS-OPD-003) to a demo hospital filled earlier, such as the hosted
Development hospital (Render and Neon): patients checked in with tokens, a walk-in, one seen, one
with the doctor, and the ones who did not come. Run it again on another day for that day's queue.

Same safety rules as the seed: only demo deployments, or with ``--hosted-development`` only the
hosted Development environment (synthetic data only). Needs the doctors' OPD sessions first
(``add_demo_doctor_schedules``). Refused when today's queue already has a patient checked in. One
transaction: stopped half-way, nothing is kept.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.demo.appointments import front_desks
from apps.demo.opd_queue import add_queue_examples
from apps.demo.seed import DemoError, check_safe
from apps.identity.accounts import active_administrators
from apps.organizations.dates import hospital_today
from apps.scheduling.models import Appointment, DoctorSchedule


class Command(BaseCommand):
    help = (
        "Add today's OPD queue (check-in, tokens, a walk-in, no-shows) to a filled demo hospital."
    )

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
        if not DoctorSchedule.objects.exists():
            raise CommandError("No doctors' OPD sessions yet: run add_demo_doctor_schedules first.")
        if Appointment.objects.filter(
            local_date=hospital_today(), token_number__isnull=False
        ).exists():
            raise CommandError("This hospital already has today's OPD queue: nothing added.")
        admin = active_administrators().order_by("date_joined").first()
        if admin is None:
            raise CommandError("Provision the hospital and fill the demo first.")
        with transaction.atomic():
            notes = add_queue_examples(actor=admin, desks=front_desks())
        if not notes:
            raise CommandError("No branch had enough patients and free slots today: nothing added.")
        self.stdout.write(self.style.SUCCESS("Added today's OPD queue:"))
        for note in notes:
            self.stdout.write(f"  {note}")
        self.stdout.write(
            "See it on OPD queue: the front desk (frontdesk.<branch>@) checks in, walks in and "
            "calls the next patient; the head of department (hod.<branch>@) sees it."
        )
