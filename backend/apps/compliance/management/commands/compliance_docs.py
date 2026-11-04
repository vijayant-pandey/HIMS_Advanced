"""Write (or check) the generated compliance documents (HIMS-COMP).

python manage.py compliance_docs          # rewrite the files
python manage.py compliance_docs --check  # exit 1 if they are out of date
"""

from django.core.management.base import BaseCommand, CommandError

from apps.compliance.docs_generator import outputs


class Command(BaseCommand):
    help = "Generate docs/compliance/requirements-matrix.md and risk-register.md."

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
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8", newline="\n")
        if check and stale:
            raise CommandError(
                f"Out of date: {', '.join(stale)}. Run `python manage.py compliance_docs`."
            )
        self.stdout.write(self.style.SUCCESS("Compliance documents up to date."))
