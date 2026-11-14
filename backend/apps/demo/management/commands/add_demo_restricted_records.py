"""Add the restricted records and emergency access examples (HIMS-PAT-006) to a demo hospital
that was filled before them, such as the hosted Development hospital (Render and Neon), which
``seed_demo_hospital`` refuses to fill twice.

Same safety rules as the seed: only demo deployments, or with ``--hosted-development`` only the
hosted Development environment (synthetic data only). Refused when the hospital already has a
restricted record. One transaction: stopped half-way, nothing is kept.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.access_control.models import RoleAssignment
from apps.demo.seed import DemoError, add_restricted_examples, check_safe
from apps.facilities.models import Facility
from apps.patients.models import Patient


def _holder(role: str, **scope):
    now = timezone.now()
    assignment = (
        RoleAssignment.objects.filter(
            role__code=role,
            revoked_at__isnull=True,
            valid_from__lte=now,
            user__is_active=True,
            support_access__isnull=True,
            **scope,
        )
        .exclude(valid_until__lte=now)
        .select_related("user")
        .order_by("created_at")
        .first()
    )
    return assignment.user if assignment else None


class Command(BaseCommand):
    help = (
        "Add restricted records and emergency access examples to an already filled demo hospital."
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
        if Patient.objects.filter(is_restricted=True).exists():
            raise CommandError("This hospital already has restricted records: nothing added.")
        records = _holder("medical-records-officer", facility__isnull=True)
        if records is None:
            raise CommandError("No medical records officer (whole hospital): fill the demo first.")
        first = Facility.objects.order_by("created_at").first()
        hod = _holder("department-head", facility=first) if first else None
        with transaction.atomic():
            examples = add_restricted_examples(records=records, hod=hod)
        if not examples:
            raise CommandError("No registered patients to restrict: fill the demo first.")
        self.stdout.write(self.style.SUCCESS("Added restricted records and emergency access:"))
        for typed, what in examples:
            self.stdout.write(f"  {typed}  ->  {what}")
        self.stdout.write(
            f"Emergency access to review: sign in as {records.email}, Patients -> Emergency access."
        )
