"""Measure the response times of the main screens against their targets (spec 18;
HIMS-OPS-017).

Developer PC only. Everything the measurement creates (a temporary account, its sign-in and
audit events) is rolled back; only the result is kept, on the Performance screen and in the
audit log. Exits with status 1 when a screen misses its target.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.performance import timings
from apps.performance.models import PerformanceCheck
from apps.performance.services import (
    PerformanceError,
    _require_local,
    dataset,
    run_response_times,
)

from ._output import mark, write_json


class Command(BaseCommand):
    help = "Measure the main screens' response times (p50/p95) against their targets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--samples",
            type=int,
            default=timings.DEFAULT_SAMPLES,
            help=f"Calls per screen after warming up (3 to {timings.MAX_SAMPLES}).",
        )
        parser.add_argument(
            "--json", help="Write the results to this file instead of keeping them."
        )
        parser.add_argument(
            "--no-fail", action="store_true", help="Exit 0 even when a screen misses its target."
        )

    def handle(self, *args, **options):
        try:
            if options["json"]:
                _require_local("Measuring response times from HIMS")
                started_at = timezone.now()
                results = timings.measure(samples=options["samples"])
                write_json(options["json"], started_at=started_at, results=results, rows=dataset())
            else:
                check = run_response_times(
                    trigger=PerformanceCheck.Trigger.COMMAND, samples=options["samples"]
                )
                results = check.results
        except PerformanceError as error:
            raise CommandError(error.detail) from error
        for item in results:
            self.stdout.write(
                f"{mark(item)} {item['label']}: p50 {item['p50_ms']:.0f} ms, "
                f"p95 {item['p95_ms']:.0f} ms (target {item['target_ms']:.0f}), "
                f"{item['queries']} queries" + (f" ({item['detail']})" if item["detail"] else "")
            )
        failed = sum(1 for item in results if not item["passed"])
        if not failed:
            self.stdout.write(self.style.SUCCESS(f"PASSED: all {len(results)} screens."))
        elif options["no_fail"]:
            self.stdout.write(self.style.WARNING(f"{failed} of {len(results)} screens missed."))
        else:
            raise CommandError(f"FAILED: {failed} of {len(results)} screens missed their target.")
