"""Write (or check) the generated data dictionary and ERDs (spec 28; HIMS-DATA-001).

python manage.py data_dictionary          # rewrite the two files
python manage.py data_dictionary --check  # exit 1 if they are out of date
"""

from django.core.management.base import BaseCommand, CommandError

from common.datadict.generator import outputs


class Command(BaseCommand):
    help = "Generate docs/architecture/data-architecture/data-dictionary.md and erd.md."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="Only check; change nothing.")

    def handle(self, *args, check=False, **options):
        stale = []
        for path, text in outputs().items():
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current.replace("\r\n", "\n") == text:
                continue
            stale.append(path.name)
            if not check:
                path.write_text(text, encoding="utf-8", newline="\n")
        if check and stale:
            raise CommandError(
                f"Out of date: {', '.join(stale)}. Run `python manage.py data_dictionary`."
            )
        verb = "Up to date" if not stale else ("Out of date" if check else "Written")
        self.stdout.write(self.style.SUCCESS(f"{verb}: data-dictionary.md, erd.md"))
