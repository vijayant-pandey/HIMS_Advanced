"""Encrypt every stored secret again with the newest key (spec 13.3; HIMS-SEC-011).

python manage.py rotate_encryption_keys --dry-run  # count what would change
python manage.py rotate_encryption_keys            # re-encrypt, then the old key can be removed
"""

from django.core.management.base import BaseCommand

from apps.compliance import encryption


class Command(BaseCommand):
    help = "Encrypt stored secrets again with the first key in HIMS_FIELD_ENCRYPTION_KEYS."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Count only; change nothing.")

    def handle(self, *args, dry_run=False, **options):
        rotated = encryption.rotate(dry_run=dry_run)
        verb = "Would encrypt again" if dry_run else "Encrypted again"
        for name, count in rotated.items():
            self.stdout.write(f"{verb}: {count} ({name})")
        left = encryption.status()["on_older_keys"]
        self.stdout.write(
            self.style.SUCCESS(f"Values still needing an older key: {left}.")
            if not dry_run
            else f"Values needing an older key now: {left}."
        )
