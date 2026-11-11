"""Check that the high-volume queries use their indexes (spec 28.6; HIMS-DATA-002).

Reads only (EXPLAIN of SELECT statements), so it is safe on any database. The result is kept on
the Performance screen and in the audit log. Exits with status 1 when a query fails, so it can
be used in scripts. For production-like volume use ``volume_check`` instead.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.performance import plans
from apps.performance.models import PerformanceCheck
from apps.performance.services import dataset, run_index_check

from ._output import mark, write_json


class Command(BaseCommand):
    help = "Check the query plans of the high-volume queries (reads only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json", help="Write the results to this file instead of keeping them."
        )
        parser.add_argument(
            "--no-fail", action="store_true", help="Exit 0 even when a query fails its check."
        )

    def handle(self, *args, **options):
        if options["json"]:
            started_at = timezone.now()
            results, _ = plans.run_index_check()
            write_json(options["json"], started_at=started_at, results=results, rows=dataset())
        else:
            check = run_index_check(trigger=PerformanceCheck.Trigger.COMMAND)
            results = check.results
        for item in results:
            used = ", ".join(item["indexes_used"]) or "no index"
            self.stdout.write(
                f"{mark(item)} {item['label']}: {item['ms']:.1f} ms, {used}"
                + (f" ({item['detail']})" if item["detail"] else "")
            )
        failed = sum(1 for item in results if not item["passed"])
        if not failed:
            self.stdout.write(self.style.SUCCESS(f"PASSED: all {len(results)} queries."))
        elif options["no_fail"]:
            self.stdout.write(self.style.WARNING(f"{failed} of {len(results)} queries failed."))
        else:
            raise CommandError(f"FAILED: {failed} of {len(results)} queries.")
