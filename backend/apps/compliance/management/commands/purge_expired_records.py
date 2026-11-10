"""Run the retention purge now (HIMS-COMP-006). The same job runs daily through Celery beat; use
this where no scheduler runs (e.g. a developer PC). ``--dry-run`` only shows what would go.
Deletes nothing while no period is set; legal holds always win."""

from django.core.management.base import BaseCommand

from apps.compliance.models import RetentionPurgeRun
from apps.compliance.retention import CATEGORIES, preview, run_purge


class Command(BaseCommand):
    help = "Delete housekeeping records past their retention period, honouring legal holds."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Show what would be deleted; delete nothing."
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            for key, plan in preview().items():
                label = CATEGORIES[key].label
                if plan["skipped"]:
                    self.stdout.write(f"{label}: {plan['skipped']}")
                else:
                    self.stdout.write(
                        f"{label}: would delete {plan['would_delete']}, "
                        f"kept by legal hold {plan['held']}"
                    )
            return
        run = run_purge(trigger=RetentionPurgeRun.Trigger.COMMAND)
        for key, plan in run.details.items():
            more = " (more next run)" if plan["more_left"] else ""
            self.stdout.write(
                f"{CATEGORIES[key].label}: {plan['skipped'] or plan['deleted']}{more}"
            )
        self.stdout.write(self.style.SUCCESS(f"Deleted {run.deleted_total} record(s)."))
