"""Add the appointments (HIMS-OPD-002) to a demo hospital that was filled before them, such as the
hosted Development hospital (Render and Neon), which ``seed_demo_hospital`` refuses to fill twice.

Same safety rules as the seed: only demo deployments, or with ``--hosted-development`` only the
hosted Development environment (synthetic data only). Needs the doctors' OPD sessions first
(``add_demo_doctor_schedules``). Refused when the hospital already has an appointment. One
transaction: stopped half-way, nothing is kept.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.demo.appointments import add_appointment_examples, front_desks
from apps.demo.seed import DemoError, check_safe
from apps.identity.accounts import active_administrators
from apps.scheduling.models import Appointment, DoctorSchedule


class Command(BaseCommand):
    help = (
        "Add appointments (booked, moved, cancelled, to move) to an already filled demo hospital."
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
        if Appointment.objects.exists():
            raise CommandError("This hospital already has appointments: nothing added.")
        if not DoctorSchedule.objects.exists():
            raise CommandError("No doctors' OPD sessions yet: run add_demo_doctor_schedules first.")
        admin = active_administrators().order_by("date_joined").first()
        if admin is None:
            raise CommandError("Provision the hospital and fill the demo first.")
        with transaction.atomic():
            notes = add_appointment_examples(actor=admin, desks=front_desks())
        booked = Appointment.objects.count()
        if not booked:
            raise CommandError("No free slots in the next two weeks: nothing added.")
        self.stdout.write(self.style.SUCCESS(f"Added {booked} appointments:"))
        for note in notes:
            self.stdout.write(f"  {note}")
        self.stdout.write(
            "See them on Appointments: the front desk (frontdesk.<branch>@) or the OPD scheduler "
            "(opd.<branch>@) books, moves and cancels; the head of department (hod.<branch>@) "
            "sees them."
        )
