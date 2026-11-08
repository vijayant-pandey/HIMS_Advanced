"""Back up the database and the stored documents now (HIMS-OPS-009; developer PC only).

The backup goes into a new folder inside HIMS_BACKUP_DIR and is listed on the Backups screen.
Then run ``python manage.py restore_drill`` to prove it can be restored.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.recovery.pg_tools import RecoveryError
from apps.recovery.services import backup_folder, create_backup


class Command(BaseCommand):
    help = "Back up the database and the stored documents (developer PC only)."

    def handle(self, *args, **options):
        try:
            backup = create_backup()
        except RecoveryError as error:
            raise CommandError(error.detail) from error
        self.stdout.write(
            self.style.SUCCESS(
                f"Backup {backup.name} made in {backup.seconds:.1f} s: {backup.tables} tables, "
                f"{backup.rows} rows, {backup.documents} document file(s)."
            )
        )
        self.stdout.write(f"Folder: {backup_folder() / backup.name}")
