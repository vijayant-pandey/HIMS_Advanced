"""Create the demo hospitals on this PC: 5 Indian and 5 US hospitals, 3 branches each, every one
with its own database (HIMS-QA-004). See docs/testing/demo-hospitals.md.

    set HIMS_DEMO_PASSWORD=<a password for all demo accounts>
    python manage.py setup_demo_hospitals --password-env HIMS_DEMO_PASSWORD

``--only in-sunrise`` builds one; ``--reset`` builds again from scratch (the old demo data is
lost); ``--small`` makes a quick, smaller version.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.demo.hospitals import all_hospitals, by_key
from apps.demo.seed import DemoError
from apps.demo.setup import set_up


class Command(BaseCommand):
    help = "Create the demo hospitals (own database each) and fill them with synthetic records."

    def add_arguments(self, parser):
        parser.add_argument("--password-env", required=True)
        parser.add_argument("--only", action="append", help="Only this hospital (repeatable)")
        parser.add_argument("--reset", action="store_true", help="Build again from scratch")
        parser.add_argument("--small", action="store_true", help="One branch, fewer records")

    def handle(self, *args, **opts):
        try:
            hospitals = (
                [by_key(key) for key in opts["only"]] if opts["only"] else list(all_hospitals())
            )
        except KeyError as exc:
            raise CommandError(str(exc)) from exc
        failed = []
        for hospital in hospitals:
            try:
                set_up(
                    hospital,
                    password_env=opts["password_env"],
                    reset=opts["reset"],
                    small=opts["small"],
                    say=self.stdout.write,
                )
            except DemoError as exc:
                failed.append(hospital.key)
                self.stdout.write(self.style.ERROR(f"  {hospital.display_name}: {exc}"))
        if failed:
            raise CommandError(f"Not built: {', '.join(failed)}. See the messages above.")
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(hospitals)} demo hospital(s) ready. Run 'npm run dev' in frontend and "
                "choose one in the launcher."
            )
        )
