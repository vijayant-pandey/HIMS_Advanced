"""Check stored staff documents for viruses (HIMS-SEC-013).

By default only the documents never checked (uploaded before scanning, or while only the test-file
check was on). ``--all`` checks every document again, e.g. after the virus list was updated. A
virus found blocks the file, archives the document and emails the compliance team. Up to 200 at a
time: run again for more. Safe to run any number of times.
"""

from django.core.management.base import BaseCommand

from apps.staff.documents import scan_stored_documents


class Command(BaseCommand):
    help = "Check stored staff documents for viruses (200 at a time)."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Check every document again.")

    def handle(self, *args, **options):
        counts = scan_stored_documents(only_unchecked=not options["all"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Checked {counts['checked']}: {counts['clean']} without a virus, "
                f"{counts['infected']} with a virus (blocked), {counts['not_checked']} that this "
                f"scanner cannot really check, {counts['missing']} missing."
            )
        )
