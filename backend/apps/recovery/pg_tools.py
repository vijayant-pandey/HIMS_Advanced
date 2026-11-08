"""PostgreSQL's own backup tools, ``pg_dump`` and ``pg_restore`` (HIMS-OPS-009).

Where the tools are taken from (first match wins):

1. ``HIMS_PG_DOCKER_CONTAINER``: run them inside that container with ``docker exec`` (the
   database container of ``docker-compose.yml``, and the database service in CI). They then
   connect through the container's own socket, so host and port are not used.
2. ``HIMS_PG_BIN_DIR``: the folder holding them.
3. The ``PATH``.
4. On Windows: the newest ``C:\\Program Files\\PostgreSQL\\<version>\\bin``.

The tools must be the same major version as the database server or newer. The password is
handed over in the environment (``PGPASSWORD``), never on the command line, and error output is
passed through the log filter before it is shown or kept.
"""

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import psycopg
from django.conf import settings
from django.db import connections

from common.exceptions import ConflictError
from common.log_safety import scrub

TIMEOUT_SECONDS = 3600
_WINDOWS_ROOT = Path("C:/Program Files/PostgreSQL")
# Django-only connection options that libpq does not understand.
_DJANGO_OPTIONS = {"pool", "isolation_level", "server_side_binding", "assume_role", "context"}


class RecoveryError(ConflictError):
    code = "RECOVERY_FAILED"
    title = "Backup or restore could not be completed"


@dataclass(frozen=True)
class Tools:
    """How to start the tools, and a short description of where they came from."""

    prefix: tuple[str, ...]  # e.g. ("docker", "exec", "-i", "-e", "PGPASSWORD", "abc123")
    source: str
    in_container: bool

    def command(self, tool: str, *args: str) -> list[str]:
        if self.in_container:
            return [*self.prefix, tool, *args]
        return [str(Path(self.prefix[0]) / _exe(tool)) if self.prefix else tool, *args]


def _exe(tool: str) -> str:
    return f"{tool}.exe" if os.name == "nt" else tool


def _windows_bin() -> Path | None:
    if os.name != "nt" or not _WINDOWS_ROOT.is_dir():
        return None
    found = [p.parent for p in _WINDOWS_ROOT.glob("*/bin/pg_restore.exe")]
    numbered = [p for p in found if re.fullmatch(r"\d+(\.\d+)?", p.parent.name)]
    return max(numbered, key=lambda p: float(p.parent.name), default=None)


def find_tools() -> Tools:
    """Where pg_dump and pg_restore are, or a clear error saying how to provide them."""
    container = settings.HIMS_PG_DOCKER_CONTAINER
    if container:
        return Tools(("docker", "exec", "-i", "-e", "PGPASSWORD", container), "container", True)
    folder = settings.HIMS_PG_BIN_DIR
    if folder:
        if not (Path(folder) / _exe("pg_restore")).is_file():
            raise RecoveryError(f"HIMS_PG_BIN_DIR does not hold pg_dump and pg_restore: {folder}")
        return Tools((folder,), "HIMS_PG_BIN_DIR", False)
    on_path = shutil.which("pg_restore")
    if on_path and shutil.which("pg_dump"):
        return Tools((str(Path(on_path).parent),), "PATH", False)
    windows = _windows_bin()
    if windows is not None:
        return Tools((str(windows),), "PostgreSQL install folder", False)
    raise RecoveryError(
        "PostgreSQL's backup tools (pg_dump, pg_restore) were not found on this computer. "
        "Install PostgreSQL (or its command line tools), or set HIMS_PG_BIN_DIR to their folder."
    )


def tools_version(tools: Tools) -> str:
    result = _run(tools.command("pg_dump", "--version"), tool="pg_dump", database={}, timeout=60)
    return result.stdout.decode(errors="replace").strip()


def database_settings(alias: str = "default") -> dict:
    """Connection settings for backups and drills: the owner's user when separate database users
    are set up (HIMS-OPS-007), because a drill creates a database and the app's user may not."""
    database = dict(connections.databases[alias])
    owner = settings.HIMS_OWNER_DATABASE
    if alias == "default" and owner:
        database.update(USER=owner.get("USER", ""), PASSWORD=owner.get("PASSWORD", ""))
    return database


def connect(database: dict, *, name: str | None = None, autocommit: bool = True):
    """A plain psycopg connection (outside Django's transaction handling)."""
    params = {
        "dbname": name or database["NAME"],
        "user": database.get("USER") or None,
        "password": database.get("PASSWORD") or None,
        "host": database.get("HOST") or None,
        "port": str(database["PORT"]) if database.get("PORT") else None,
    }
    for key, value in (database.get("OPTIONS") or {}).items():
        if key not in _DJANGO_OPTIONS:
            params[key] = value
    return psycopg.connect(
        **{k: v for k, v in params.items() if v is not None}, autocommit=autocommit
    )


def _connection_args(tools: Tools, database: dict, name: str) -> list[str]:
    args = ["--no-password", f"--dbname={name}"]
    if database.get("USER"):
        args.append(f"--username={database['USER']}")
    if not tools.in_container:
        if database.get("HOST"):
            args.append(f"--host={database['HOST']}")
        if database.get("PORT"):
            args.append(f"--port={database['PORT']}")
    return args


def _run(command, *, tool: str, database: dict, stdin=None, stdout=None, timeout=TIMEOUT_SECONDS):
    env = {**os.environ}
    if database.get("PASSWORD"):
        env["PGPASSWORD"] = str(database["PASSWORD"])
    try:
        result = subprocess.run(  # noqa: S603 - fixed tool names, no shell
            command,
            stdin=stdin,
            stdout=stdout if stdout is not None else subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RecoveryError(f"{tool} could not run: {type(exc).__name__}") from exc
    if result.returncode != 0:
        detail = scrub(result.stderr.decode(errors="replace").strip())[:500]
        raise RecoveryError(f"{tool} failed: {detail or 'no message'}")
    return result


def dump(tools: Tools, database: dict, out_path: Path, *, snapshot: str) -> None:
    """The whole database in PostgreSQL's custom format, exactly as of ``snapshot``."""
    command = tools.command(
        "pg_dump",
        "--format=custom",
        f"--snapshot={snapshot}",
        *_connection_args(tools, database, database["NAME"]),
    )
    with open(out_path, "wb") as out:
        _run(command, tool="pg_dump", database=database, stdout=out)


def restore(tools: Tools, database: dict, dump_path: Path, *, into: str) -> None:
    """Restore a dump into the (new, empty) database ``into``. Stops at the first error."""
    command = tools.command(
        "pg_restore",
        "--exit-on-error",
        "--no-owner",
        "--no-privileges",
        *_connection_args(tools, database, into),
    )
    with open(dump_path, "rb") as source:
        _run(command, tool="pg_restore", database=database, stdin=source)
