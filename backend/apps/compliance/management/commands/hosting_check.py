"""Print what this server still needs before it hosts HIMS (spec 17, 30, 31; HIMS-OPS-020).

python manage.py hosting_check              # exit 1 when a check fails
python manage.py hosting_check --real-data  # exit 1 also when a check is only fine for test data
"""

from django.core.management.base import BaseCommand, CommandError

from apps.compliance import hosting

MARKS = {hosting.OK: "OK  ", hosting.WARN: "WARN", hosting.FAIL: "FAIL"}


class Command(BaseCommand):
    help = "Check this environment against the hosting needs of HIMS."

    def add_arguments(self, parser):
        parser.add_argument(
            "--real-data",
            action="store_true",
            help="Also fail on checks that are only acceptable with synthetic test data.",
        )

    def handle(self, *args, real_data=False, **options):
        result = hosting.readiness()
        for check in result["checks"]:
            self.stdout.write(f"{MARKS[check['status']]}  {check['label']}: {check['detail']}")
            if check["fix"]:
                self.stdout.write(f"      Fix: {check['fix']}")
        self.stdout.write(
            f"\n{result['failing']} failing, {result['before_real_data']} needed before real "
            f"patient data ({result['environment']})."
        )
        if result["failing"] or (real_data and result["before_real_data"]):
            raise CommandError("This environment is not ready.")
