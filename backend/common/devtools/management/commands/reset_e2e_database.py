"""Drop and recreate the throw-away database used by the browser tests (HIMS-QA-001).

Refuses to run unless all of these hold, so it can never touch a real hospital database:

* the process is a local or test environment (``HIMS_ENVIRONMENT``);
* the configured database name starts with ``hims_e2e``;
* the database server is on this machine (``validate_environment`` already enforces that for
  local/test processes).

Then run ``migrate`` and ``provision_organization`` as usual (frontend/e2e/start-backend.mjs
does all three).
"""

import psycopg
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from psycopg import sql

from common.environment import LOCAL_ENVIRONMENTS

PREFIX = "hims_e2e"


def check_safe(environment: str, name: str) -> None:
    if environment not in LOCAL_ENVIRONMENTS:
        raise CommandError(f"Refused: HIMS_ENVIRONMENT is '{environment}', not local or test.")
    if not name.startswith(PREFIX):
        raise CommandError(f"Refused: database '{name}' does not start with '{PREFIX}'.")


class Command(BaseCommand):
    help = "Recreate the empty browser-test database (name must start with hims_e2e)."

    def handle(self, *args, **options):
        database = settings.DATABASES["default"]
        name = database["NAME"]
        check_safe(settings.HIMS_ENVIRONMENT, name)
        connections.close_all()
        params = {
            "host": database.get("HOST") or "localhost",
            "port": database.get("PORT") or 5432,
            "user": database.get("USER") or None,
            "password": database.get("PASSWORD") or None,
            "dbname": "postgres",
            "autocommit": True,
        }
        with psycopg.connect(**{k: v for k, v in params.items() if v is not None}) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        self.stdout.write(self.style.SUCCESS(f"Recreated empty database {name}."))
