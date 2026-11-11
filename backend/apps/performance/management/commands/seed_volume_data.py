"""Fill the throw-away database ``hims_volume`` with production-like synthetic records
(HIMS-DATA-002). Refuses any other database. Normally started by ``volume_check``."""

from django.core.management.base import BaseCommand, CommandError

from apps.performance.volume import VolumeError, seed


class Command(BaseCommand):
    help = "Add production-like synthetic records (only into hims_volume)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--scale", type=float, default=1.0, help="Multiply every count (0.1 = a tenth)."
        )

    def handle(self, *args, **options):
        if not 0 < options["scale"] <= 20:
            raise CommandError("--scale must be above 0 and at most 20.")
        try:
            added = seed(scale=options["scale"], progress=self.stdout.write)
        except VolumeError as error:
            raise CommandError(str(error)) from error
        total = sum(added.values())
        details = ", ".join(f"{table} {rows:,}" for table, rows in added.items())
        self.stdout.write(self.style.SUCCESS(f"Added {total:,} synthetic rows: {details}."))
