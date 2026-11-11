"""The index check and the response times at production-like volume (spec 18, 28.6;
HIMS-DATA-002, HIMS-OPS-017).

1. Creates a separate, throw-away database ``hims_volume`` on the same server (the hospital's own
   database is only read, to copy its country and time zone, and written to for the results).
2. Migrates it and fills it with synthetic records the size of a 500-bed hospital.
3. Runs ``check_query_plans`` and ``measure_response_times`` there.
4. Records both results in this hospital's database (Performance screen, audit log).
5. Removes the copy (keep it with ``--keep``; remove it later with ``--remove-copy``).

Developer PC only. Takes a few minutes; ``--scale 0.1`` for a quick look.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.performance import timings
from apps.performance.models import PerformanceCheck
from apps.performance.services import PerformanceError, remove_volume_copy, run_volume_check


class Command(BaseCommand):
    help = "Check indexes and response times on a throw-away copy with production-like volume."

    def add_arguments(self, parser):
        parser.add_argument("--scale", type=float, default=1.0, help="Multiply every count.")
        parser.add_argument("--samples", type=int, default=timings.DEFAULT_SAMPLES)
        parser.add_argument("--keep", action="store_true", help="Keep the copy afterwards.")
        parser.add_argument(
            "--remove-copy", action="store_true", help="Only remove a copy kept earlier."
        )

    def handle(self, *args, **options):
        try:
            if options["remove_copy"]:
                remove_volume_copy()
                self.stdout.write(self.style.SUCCESS("Removed the throw-away copy."))
                return
            checks = run_volume_check(
                scale=options["scale"],
                samples=options["samples"],
                keep=options["keep"],
                say=self.stdout.write,
            )
        except PerformanceError as error:
            raise CommandError(error.detail) from error
        failed = [check for check in checks if check.outcome == PerformanceCheck.Outcome.FAILED]
        for check in checks:
            style = self.style.ERROR if check in failed else self.style.SUCCESS
            self.stdout.write(style(f"{check.get_kind_display()}: {check.summary}."))
            for item in check.results:
                if not item.get("passed"):
                    self.stdout.write(f"  FAIL {item['label']}: {item['detail']}")
        self.stdout.write("The results are on the Performance screen.")
        if failed:
            raise CommandError("FAILED: see the results above.")
