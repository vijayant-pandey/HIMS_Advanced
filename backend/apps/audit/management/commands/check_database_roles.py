"""Check that the app runs with its own limited database user (HIMS-OPS-007).

Prints every check and exits with status 1 when one fails, so a deployment can stop before
the app starts with too many rights. The same checks are on the Compliance page.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from common import database_roles


class Command(BaseCommand):
    help = "Check that the app's database user cannot change the schema or the audit log."

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            result = database_roles.inspect(cursor)
        for check in result["checks"]:
            mark = "ok  " if check["passed"] else "FAIL"
            detail = f" ({check['detail']})" if check["detail"] else ""
            self.stdout.write(f"{mark} {check['label']}{detail}")
        if all(check["passed"] for check in result["checks"]) and result["set_up"]:
            self.stdout.write(self.style.SUCCESS("PASSED: database access is separated."))
            return
        if not result["set_up"]:
            self.stdout.write(
                "Set up the separate users with: python manage.py setup_database_roles "
                "--write-env  (see docs/workflows/database-users.md)"
            )
        raise CommandError("FAILED: the app's database user has more rights than it needs.")
