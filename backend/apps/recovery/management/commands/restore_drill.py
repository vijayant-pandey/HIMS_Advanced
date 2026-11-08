"""Restore a backup into a separate copy and check everything came back (HIMS-OPS-009).

The live database and documents are never touched: the copy is a new database and folder, both
removed at the end. The result is kept on the Backups screen and in the audit log. Exits with
status 1 when a check fails, so it can be used in scripts.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.recovery.models import Backup, RestoreDrill
from apps.recovery.pg_tools import RecoveryError
from apps.recovery.services import run_restore_drill


class Command(BaseCommand):
    help = "Restore a backup into a separate copy and check it (developer PC only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--backup", help="Name of the backup folder to restore (default: the newest)."
        )

    def handle(self, *args, **options):
        backups = Backup.objects.order_by("-created_at")
        if options["backup"]:
            backups = backups.filter(name=options["backup"])
        backup = backups.first()
        if backup is None:
            raise CommandError("No such backup. Make one with: python manage.py backup_database")
        try:
            drill = run_restore_drill(backup=backup, trigger=RestoreDrill.Trigger.COMMAND)
        except RecoveryError as error:
            raise CommandError(error.detail) from error
        for check in drill.checks:
            mark = "ok  " if check["passed"] else "FAIL"
            detail = f" ({check['detail']})" if check["detail"] else ""
            self.stdout.write(f"{mark} {check['label']}{detail}")
        summary = f"restored in {drill.restore_seconds:.1f} s; backup {backup.name}"
        if drill.outcome == RestoreDrill.Outcome.PASSED:
            self.stdout.write(self.style.SUCCESS(f"PASSED: everything came back ({summary})."))
            return
        raise CommandError(f"FAILED: {drill.problem_count} check(s) failed ({summary}).")
