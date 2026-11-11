"""Write (or check) the per-endpoint API contracts and the traceability matrix (HIMS-DOC-001).

python manage.py api_contracts          # rewrite the files
python manage.py api_contracts --check  # exit 1 if they are out of date
"""

from django.core.management.base import BaseCommand, CommandError

from common.contracts import generator


class Command(BaseCommand):
    help = (
        "Generate docs/architecture/api-and-integrations/endpoints/ and "
        "docs/requirements/traceability.md."
    )

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="Only check; change nothing.")

    def handle(self, *args, check=False, **options):
        files = generator.render()
        stale = generator.stale_files(files)
        if check and stale:
            names = ", ".join(path.name for path in stale)
            raise CommandError(f"Out of date: {names}. Run `python manage.py api_contracts`.")
        if stale and not check:
            generator.write(files)
        verb = "Up to date" if not stale else ("Out of date" if check else "Written")
        self.stdout.write(
            self.style.SUCCESS(f"{verb}: {len(files)} contract and traceability files")
        )
