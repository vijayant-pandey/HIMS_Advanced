"""Show the invented patients of a demo hospital (HIMS-QA-004), ready for Phase 2.

Prints (or saves as CSV) the invented patients; no database is used. Since HIMS-PAT-001 the demo
seed registers these same patients, so they are also on the Patients screen.
"""

import csv
from dataclasses import asdict, fields

from django.core.management.base import BaseCommand, CommandError

from apps.demo.hospitals import by_key
from apps.demo.patients import DemoPatient, patients_for


class Command(BaseCommand):
    help = "Show or save the invented patients of a demo hospital (registered in Phase 2)."

    def add_arguments(self, parser):
        parser.add_argument("--hospital", required=True)
        parser.add_argument("--per-branch", type=int, default=40)
        parser.add_argument("--csv", help="Save to this CSV file instead of printing")

    def handle(self, *args, **opts):
        try:
            hospital = by_key(opts["hospital"])
        except KeyError as exc:
            raise CommandError(str(exc)) from exc
        rows = [asdict(p) for p in patients_for(hospital, opts["per_branch"])]
        names = [f.name for f in fields(DemoPatient)]
        if opts["csv"]:
            with open(opts["csv"], "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=names)
                writer.writeheader()
                writer.writerows(rows)
            self.stdout.write(self.style.SUCCESS(f"Saved {len(rows)} patients to {opts['csv']}."))
            return
        writer = csv.DictWriter(self.stdout, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)
