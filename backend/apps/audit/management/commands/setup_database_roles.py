"""Create the separate database users and give each exactly its rights (HIMS-OPS-007).

Run with the owner's credentials (the current DATABASE_URL the first time, afterwards
HIMS_MIGRATION_DATABASE_URL, which this command uses automatically). Safe to run again.

On a developer PC ``--write-env`` does everything: new random passwords, the users and their
rights, and the env file updated (DATABASE_URL becomes the app's own user, the old owner URL moves
to HIMS_MIGRATION_DATABASE_URL, a copy of the old file is kept). No password is ever printed.

Hosted environments pass the passwords from the secret manager instead:
HIMS_APP_DATABASE_PASSWORD and HIMS_READONLY_DATABASE_PASSWORD.
"""

import os
import secrets
import shutil
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.audit.services import AuditAction, record_audit_event
from common import database_roles
from common.environment import LOCAL_ENVIRONMENTS


def _url(database: dict, user: str, password: str) -> str:
    host = database.get("HOST") or "localhost"
    port = database.get("PORT") or 5432
    login = f"{quote(user, safe='')}:{quote(password, safe='')}"
    return f"postgres://{login}@{host}:{port}/{database['NAME']}"


def _set(lines: list[str], key: str, value: str, *, keep_existing: bool = False) -> list[str]:
    for index, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == key:
            if not keep_existing:
                lines[index] = f"{key}={value}"
            return lines
    return [*lines, f"{key}={value}"]


class Command(BaseCommand):
    help = "Create the app, read-only and break-glass database users with least rights."

    def add_arguments(self, parser):
        parser.add_argument(
            "--write-env",
            action="store_true",
            help="Developer PC: make new passwords and update the env file in use (.env or "
            "HIMS_ENV_FILE). Nothing secret is printed.",
        )
        parser.add_argument(
            "--env-file",
            help="The env file --write-env updates (default: the one in use).",
        )
        parser.add_argument(
            "--grants-only",
            action="store_true",
            help="Only re-apply the rights (users and passwords stay as they are).",
        )

    def handle(self, *args, write_env, grants_only, env_file, **options):
        names = database_roles.role_names()
        with connection.cursor() as cursor:
            current = database_roles._one(cursor, "SELECT current_user")
        if current in (names.app, names.readonly):
            raise CommandError(
                f"Connected as {current}. Run this with the owner's credentials "
                "(HIMS_MIGRATION_DATABASE_URL)."
            )
        if write_env and settings.HIMS_ENVIRONMENT not in LOCAL_ENVIRONMENTS:
            raise CommandError("--write-env is for a developer PC; use the secret manager here.")

        if write_env:
            app_password, readonly_password = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        else:
            app_password = os.environ.get("HIMS_APP_DATABASE_PASSWORD", "")
            readonly_password = os.environ.get("HIMS_READONLY_DATABASE_PASSWORD", "")
            if not grants_only and not (app_password and readonly_password):
                raise CommandError(
                    "Give the passwords in HIMS_APP_DATABASE_PASSWORD and "
                    "HIMS_READONLY_DATABASE_PASSWORD, or use --write-env on a developer PC."
                )

        with transaction.atomic(), connection.cursor() as cursor:
            if not grants_only:
                database_roles.create_or_update_roles(
                    cursor,
                    names,
                    app_password=app_password,
                    readonly_password=readonly_password,
                )
            granted = database_roles.apply_grants(cursor, names)
            if not granted["applied"]:
                raise CommandError(f"The app's user {names.app} does not exist yet.")
            record_audit_event(
                action=AuditAction.DATABASE_USERS_SET_UP,
                resource_type="database",
                resource_id=connection.settings_dict["NAME"],
                metadata={
                    "app_user": names.app,
                    "readonly_user": names.readonly,
                    "breakglass_user": names.breakglass,
                    "tables": granted["tables"],
                    "evidence_tables": granted["evidence_tables"],
                    "passwords_changed": not grants_only,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Database users ready: {names.app} (app), {names.readonly} (read-only), "
                f"{names.breakglass} (break-glass, switched off). "
                f"{granted['tables']} tables; add-only for the app: "
                f"{', '.join(granted['evidence_tables'])}."
            )
        )
        if write_env:
            default = Path(settings.BASE_DIR) / os.environ.get("HIMS_ENV_FILE", ".env")
            path = Path(env_file) if env_file else default
            self._write_env(path, app_password, readonly_password, names)

    def _write_env(self, path: Path, app_password: str, readonly_password: str, names) -> None:
        text = path.read_bytes().decode("utf-8")
        newline = "\r\n" if "\r\n" in text else "\n"  # keep the file's own line endings
        shutil.copy2(path, path.with_name(f"{path.name}.before-database-users"))
        lines = text.splitlines()
        owner_url = next(
            (
                line.split("=", 1)[1]
                for line in lines
                if line.split("=", 1)[0].strip() == "DATABASE_URL"
            ),
            "",
        )
        database = connection.settings_dict
        if not settings.HIMS_MIGRATION_DATABASE_URL:  # first time: the old URL is the owner's
            lines = _set(lines, "HIMS_MIGRATION_DATABASE_URL", owner_url, keep_existing=True)
        lines = _set(lines, "DATABASE_URL", _url(database, names.app, app_password))
        lines = _set(
            lines, "HIMS_READONLY_DATABASE_URL", _url(database, names.readonly, readonly_password)
        )
        path.write_bytes((newline.join(lines) + newline).encode("utf-8"))
        self.stdout.write(
            f"Updated {path.name}: DATABASE_URL now uses {names.app}; migrate uses the owner "
            f"(HIMS_MIGRATION_DATABASE_URL); reports can use HIMS_READONLY_DATABASE_URL. "
            f"The old file is kept as {path.name}.before-database-users. Restart HIMS."
        )
