"""Create the ten demo hospitals on the developer PC (HIMS-QA-004).

Each demo hospital is a separate deployment with its own database, exactly as a real customer
(ADR-003, ADR-009): ``hims_demo_<key>`` on the local PostgreSQL server and a settings file
``backend/.env.demo-<key>`` (Git ignores it). For each one this:

1. creates (or, with ``reset``, re-creates) the database, with the owner's user from this PC's
   own settings;
2. writes the settings file: its own secret key, cookies, address and ports;
3. runs ``migrate``, ``provision_organization`` (administrator, auditor and the software
   supplier's support account) and ``seed_demo_hospital`` in that deployment.

The launcher (``npm run dev``) then lists the demo hospitals. Developer PC only.
"""

import os
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import psycopg
from django.conf import settings

from common.environment import LOCAL_ENVIRONMENTS
from common.log_safety import scrub

from .hospitals import Hospital
from .seed import SUPPLIER_EMAIL, DemoError

# Settings this PC's own hospital put into the environment: a demo deployment must never
# inherit them (real environment variables win over the settings file).
_INHERITED_PREFIXES = ("HIMS_", "DJANGO_", "DATABASE_URL", "REDIS_URL", "CELERY_")


def _owner_database() -> dict:
    from apps.recovery.pg_tools import database_settings

    return database_settings()


def _url(database: dict, name: str) -> str:
    user = quote(database.get("USER") or "", safe="")
    password = quote(database.get("PASSWORD") or "", safe="")
    credentials = f"{user}:{password}@" if password else (f"{user}@" if user else "")
    host = database.get("HOST") or "localhost"
    port = database.get("PORT") or 5432
    return f"postgres://{credentials}{host}:{port}/{name}"


def _require_local() -> None:
    if settings.HIMS_ENVIRONMENT not in LOCAL_ENVIRONMENTS:
        raise DemoError("Demo hospitals are made on a developer PC only (HIMS_ENVIRONMENT=local).")


def database_exists(database: dict, name: str) -> bool:
    from apps.recovery.pg_tools import connect

    with connect(database, name="postgres") as admin:
        row = admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", [name]).fetchone()
    return row is not None


def _create_database(database: dict, name: str, *, reset: bool) -> None:
    from apps.recovery.pg_tools import connect

    try:
        with connect(database, name="postgres") as admin:
            if reset:
                admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            admin.execute(f'CREATE DATABASE "{name}" TEMPLATE template0')
    except psycopg.Error as exc:
        raise DemoError(
            f"The database {name} could not be created (the database user needs permission to "
            f"create databases): {scrub(str(exc))[:200]}"
        ) from exc


def env_text(hospital: Hospital, database_url: str) -> str:
    cookie = hospital.key.replace("-", "_")
    return "\n".join(
        [
            "# Demo hospital (HIMS-QA-004): synthetic data only. Written by setup_demo_hospitals.",
            "# Gitignored: never commit this file.",
            "HIMS_ENVIRONMENT=local",
            f"HIMS_DEPLOYMENT_ID={hospital.deployment_id}",
            "DJANGO_SETTINGS_MODULE=config.settings.local",
            f"DJANGO_SECRET_KEY={secrets.token_urlsafe(50)}",
            f"DATABASE_URL={database_url}",
            "HIMS_MIGRATION_DATABASE_URL=",
            "HIMS_READONLY_DATABASE_URL=",
            "REDIS_URL=",
            f"HIMS_SESSION_COOKIE_NAME=hims_demo_{cookie}_session",
            f"HIMS_CSRF_COOKIE_NAME=hims_demo_{cookie}_csrftoken",
            f"HIMS_APP_BASE_URL=http://localhost:{hospital.frontend_port}",
            "# Demo only: sign in without setting up two-factor. Real hospitals always need it.",
            "HIMS_MFA_REQUIRED_FOR_PRIVILEGED=false",
            "",
        ]
    )


def _values(text: str) -> dict[str, str]:
    values = {}
    for line in text.splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def child_env(env_file: str, values: dict[str, str], password_env: str) -> dict:
    """A clean environment for one demo deployment: nothing from this PC's hospital leaks in."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(_INHERITED_PREFIXES)}
    env.update(values)
    env.update(
        HIMS_ENV_FILE=env_file,
        HIMS_TRACING_EXPORTER="none",
        PYTHONIOENCODING="utf-8",
    )
    if password_env in os.environ:
        env[password_env] = os.environ[password_env]
    return env


def _manage(env: dict, *args: str, say) -> None:
    command = [sys.executable, str(Path(settings.BASE_DIR) / "manage.py"), *args]
    result = subprocess.run(  # noqa: S603 - our own manage.py with fixed arguments
        command,
        cwd=settings.BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=3600,
        check=False,
    )
    for line in result.stdout.splitlines():
        say(f"    {line}")
    if result.returncode != 0:
        tail = scrub(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "")
        raise DemoError(f"'{args[0]}' failed: {tail[:300]}")


def set_up(hospital: Hospital, *, password_env: str, reset: bool, small: bool, say=print) -> None:
    _require_local()
    if not os.environ.get(password_env):
        raise DemoError(f"Set {password_env} to the password for the demo accounts first.")
    database = _owner_database()
    env_path = Path(settings.BASE_DIR) / hospital.env_file
    if database_exists(database, hospital.database) and not reset:
        raise DemoError(
            f"{hospital.display_name} already exists (database {hospital.database}). "
            "Use --reset to build it again from scratch."
        )
    say(f"{hospital.display_name}: creating database {hospital.database}...")
    _create_database(database, hospital.database, reset=reset)
    text = env_text(hospital, _url(database, hospital.database))
    env_path.write_text(text, encoding="utf-8")
    env = child_env(hospital.env_file, _values(text), password_env)
    say("  updating the database tables (migrate)...")
    _manage(env, "migrate", "--no-input", "-v", "0", say=say)
    say("  creating the hospital and its first accounts...")
    _manage(
        env,
        "provision_organization",
        f"--legal-name={hospital.legal_name}",
        f"--display-name={hospital.display_name}",
        f"--country={hospital.country}",
        f"--timezone={hospital.timezone}",
        f"--currency={hospital.currency}",
        f"--admin-email={hospital.admin_email}",
        "--admin-name=Demo Hospital Administrator",
        f"--admin-password-env={password_env}",
        f"--auditor-email={hospital.auditor_email}",
        "--auditor-name=Demo Auditor",
        f"--auditor-password-env={password_env}",
        f"--support-email={SUPPLIER_EMAIL}",
        "--support-name=HIMS Supplier Support (demo)",
        f"--support-password-env={password_env}",
        say=say,
    )
    say("  filling it with demo records (a few minutes)...")
    _manage(
        env,
        "seed_demo_hospital",
        f"--hospital={hospital.key}",
        f"--password-env={password_env}",
        *(["--small"] if small else []),
        say=say,
    )
    say(f"  ready: http://localhost:{hospital.frontend_port} (start it from the launcher)")
