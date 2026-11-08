"""Backups and restore drills (spec 13.5 "a database restore recovers records but fails to
restore required audit relationships", 17.3, 23, 27.1; HIMS-OPS-009).
See docs/workflows/backup-and-restore.md.

**Backup:** the database and the stored documents, from one moment. The database is copied by
PostgreSQL's ``pg_dump`` inside a snapshot, and the inventory (row counts and fingerprints per
table, migrations, constraints, triggers, indexes, sequences, audit chain head, document
fingerprints) is taken inside the *same* snapshot, so it describes exactly what the copy holds.

**Restore drill:** the backup is restored into a new, separate database and a separate folder
(the live database and documents are never touched), then checked: every table with the same
rows, every rule of the database (constraints, triggers protecting the audit log), the audit
chain verified with this deployment's keys, the audit records' links, encrypted values readable
with the keys kept outside the database, and every document present and unchanged. Then the copy
is removed. The result is kept as evidence (append-only) and written to the audit log.

Only on a developer PC or in tests: in hosted environments the cloud database service takes the
backups and the drill follows the cloud runbook (HIMS-OPS-004, waits for AWS).
"""

import hashlib
import json
import logging
import re
import shutil
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import psycopg
from django.conf import settings
from django.db import DatabaseError, connections
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction, record_audit_event
from common import crypto
from common.environment import LOCAL_ENVIRONMENTS
from common.log_safety import scrub

from . import pg_tools
from .inventory import AUDIT_TABLES, describe, encrypted_samples
from .models import Backup, RestoreDrill
from .pg_tools import RecoveryError

logger = logging.getLogger(__name__)

DUMP_FILE = "database.dump"
MANIFEST_FILE = "manifest.json"
DOCUMENTS_FOLDER = "documents"
DRILL_ALIAS = "hims_restore_drill"
MAX_NAMES_SHOWN = 20  # a check lists at most this many tables, files... by name

CHECK_LABELS = {
    "backup_file": "The backup file is complete and unchanged",
    "restore": "PostgreSQL restored the backup without errors",
    "migrations": "Same database version (migrations)",
    "tables": "Every table came back with the same rows",
    "constraints": "Every database rule came back (keys, links, uniqueness, overlaps)",
    "triggers": "Every database trigger came back and is switched on",
    "indexes": "Every index came back",
    "extensions": "Every database extension came back",
    "sequences": "Every counter came back at the same value",
    "audit_chain": "Audit log chain verified with this hospital's keys",
    "audit_relationships": "Audit records still linked: chain to records, records to people, "
    "audit tables still append-only",
    "encrypted_data": "Encrypted values can be read with the keys kept outside the database",
    "documents": "Every stored document came back unchanged",
}


def can_run_here() -> bool:
    return settings.HIMS_ENVIRONMENT in LOCAL_ENVIRONMENTS


def _require_local() -> None:
    if not can_run_here():
        raise RecoveryError(
            "Backups and restore drills from HIMS run only on a developer PC. In hosted "
            "environments the cloud database service takes the backups and the restore drill "
            "follows the cloud runbook."
        )


def backup_folder() -> Path:
    return Path(settings.HIMS_BACKUP_DIR)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _new_name() -> str:
    stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    base = re.sub(r"[^a-z0-9-]+", "-", f"hims-{settings.HIMS_DEPLOYMENT_ID}-{stamp}".lower())
    name, n = base, 1
    while (backup_folder() / name).exists() or Backup.objects.filter(name=name).exists():
        n += 1
        name = f"{base}-{n}"
    return name


def _copy_documents(target: Path) -> dict[str, dict]:
    """Copy every stored file; returns their fingerprints by relative path."""
    source = Path(settings.MEDIA_ROOT)
    files = {}
    if not source.is_dir():
        return files
    for path in sorted(p for p in source.rglob("*") if p.is_file()):
        relative = path.relative_to(source).as_posix()
        copy = target / relative
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, copy)
        files[relative] = {"sha256": _sha256(copy), "bytes": copy.stat().st_size}
    return files


# --- Backup --------------------------------------------------------------------------------


def create_backup(*, actor=None, request=None) -> Backup:
    """Back up the database and the documents now. Raises RecoveryError if it cannot."""
    _require_local()
    tools = pg_tools.find_tools()
    started = time.monotonic()
    name = _new_name()
    folder = backup_folder() / name
    database = pg_tools.database_settings()
    try:
        folder.mkdir(parents=True)
        with (
            pg_tools.connect(database) as live,
            live.cursor() as cursor,
            live.transaction(),
        ):
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            cursor.execute("SELECT pg_export_snapshot()")
            snapshot = cursor.fetchone()[0]
            manifest = describe(cursor)
            pg_tools.dump(tools, database, folder / DUMP_FILE, snapshot=snapshot)
        manifest["files"] = _copy_documents(folder / DOCUMENTS_FOLDER)
        manifest["tools"] = pg_tools.tools_version(tools)
        dump_path = folder / DUMP_FILE
        backup = Backup(
            name=name,
            created_by_id=getattr(actor, "pk", None),
            database_name=database["NAME"],
            environment=settings.HIMS_ENVIRONMENT,
            release=settings.HIMS_RELEASE,
            dump_bytes=dump_path.stat().st_size,
            dump_sha256=_sha256(dump_path),
            tables=len(manifest["tables"]),
            rows=sum(table["rows"] for table in manifest["tables"].values()),
            documents=len(manifest["files"]),
            documents_bytes=sum(f["bytes"] for f in manifest["files"].values()),
            seconds=round(time.monotonic() - started, 2),
            manifest=manifest,
        )
        (folder / MANIFEST_FILE).write_text(
            json.dumps({"backup": str(backup.id), **manifest}, indent=1, default=str),
            encoding="utf-8",
        )
    except Exception as exc:
        shutil.rmtree(folder, ignore_errors=True)
        record_audit_event(
            action=AuditAction.BACKUP_CREATED,
            resource_type="backup",
            actor=actor,
            request=request,
            outcome=AuditEvent.Outcome.FAILURE,
            metadata={"name": name, "error": type(exc).__name__},
        )
        logger.error("backup_failed", extra={"backup_name": name, "error": type(exc).__name__})
        if isinstance(exc, RecoveryError):
            raise
        raise RecoveryError(f"The backup could not be made: {scrub(str(exc))[:300]}") from exc
    backup.save()
    record_audit_event(
        action=AuditAction.BACKUP_CREATED,
        resource_type="backup",
        resource_id=backup.pk,
        actor=actor,
        request=request,
        metadata={
            "name": name,
            "tables": backup.tables,
            "rows": backup.rows,
            "documents": backup.documents,
            "bytes": backup.dump_bytes + backup.documents_bytes,
            "seconds": backup.seconds,
        },
    )
    return backup


# --- Restoring into a separate copy ----------------------------------------------------------


@dataclass
class RestoredCopy:
    """A backup restored next to the live system (never over it)."""

    database: str
    documents: Path
    alias: str = DRILL_ALIAS
    error: str = ""
    seconds: float = 0.0
    checks: list = field(default_factory=list)


def _drill_database_name(live: str) -> str:
    stamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    return f"{live[:30]}_drill_{stamp}"[:63]


@contextmanager
def restored_copy(backup: Backup) -> Iterator[RestoredCopy]:
    """Restore ``backup`` into a new database and folder; both are removed afterwards."""
    _require_local()
    tools = pg_tools.find_tools()
    database = pg_tools.database_settings()
    name = _drill_database_name(database["NAME"])
    if name == database["NAME"]:  # pragma: no cover - the suffix makes this impossible
        raise RecoveryError("Refusing to restore over the live database.")
    folder = Path(tempfile.mkdtemp(prefix="hims-restore-drill-"))
    copy = RestoredCopy(database=name, documents=folder / DOCUMENTS_FOLDER)
    try:
        with pg_tools.connect(database) as admin:
            admin.execute(f'CREATE DATABASE "{name}" TEMPLATE template0')
    except psycopg.Error as exc:
        shutil.rmtree(folder, ignore_errors=True)
        raise RecoveryError(
            "A separate database for the drill could not be created (the database user needs "
            f"permission to create databases): {scrub(str(exc))[:200]}"
        ) from exc
    connections.databases[copy.alias] = {**database, "NAME": name}
    try:
        connections[copy.alias].connect()  # opened now, so a connection problem shows first
        started = time.monotonic()
        try:
            pg_tools.restore(tools, database, backup_folder() / backup.name / DUMP_FILE, into=name)
        except RecoveryError as exc:
            copy.error = exc.detail
        source = backup_folder() / backup.name / DOCUMENTS_FOLDER
        if source.is_dir():
            shutil.copytree(source, copy.documents)
        else:
            copy.documents.mkdir(parents=True)
        copy.seconds = round(time.monotonic() - started, 2)
        yield copy
    finally:
        connections[copy.alias].close()
        del connections[copy.alias]
        connections.databases.pop(copy.alias, None)
        with pg_tools.connect(database) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        shutil.rmtree(folder, ignore_errors=True)


# --- Checks ----------------------------------------------------------------------------------


def _check(key: str, problems: list[str], *, passed_detail: str = "") -> dict:
    shown = problems[:MAX_NAMES_SHOWN]
    more = len(problems) - len(shown)
    detail = "; ".join(shown) + (f"; and {more} more" if more > 0 else "")
    return {
        "key": key,
        "label": CHECK_LABELS[key],
        "passed": not problems,
        "detail": detail if problems else passed_detail,
    }


def _compare(expected: dict, found: dict, *, what: str) -> list[str]:
    problems = [f"{what} {name} missing" for name in expected if name not in found]
    problems += [
        f"{what} {name} different"
        for name, value in expected.items()
        if name in found and found[name] != value
    ]
    problems += [f"{what} {name} not in the backup" for name in found if name not in expected]
    return problems


def _table_problems(expected: dict, found: dict) -> list[str]:
    problems = [f"{t} missing" for t in expected if t not in found]
    for table, want in expected.items():
        got = found.get(table)
        if got is None:
            continue
        if got["rows"] != want["rows"]:
            problems.append(f"{table}: {got['rows']} rows, expected {want['rows']}")
        elif got["fingerprint"] != want["fingerprint"]:
            problems.append(f"{table}: rows changed")
    return problems


def _audit_relationship_problems(expected: dict, found: dict) -> list[str]:
    want, got = expected["audit"], found["audit"]
    problems = []
    if got["links_without_event"]:
        problems.append(f"{got['links_without_event']} chain link(s) point to a missing record")
    if got["events_with_unknown_actor"] > want["events_with_unknown_actor"]:
        problems.append(
            f"{got['events_with_unknown_actor']} audit record(s) name a person who is missing"
        )
    if got["links"] != want["links"]:
        problems.append(f"{got['links']} chain link(s), expected {want['links']}")
    protected = {name for name in expected["triggers"] if name.split(".", 1)[0] in AUDIT_TABLES}
    for name in sorted(protected):
        if found["triggers"].get(name) != expected["triggers"][name]:
            problems.append(f"{name} no longer protects the audit log")
    return problems


def _audit_chain_check(copy: RestoredCopy, expected: dict) -> dict:
    from apps.audit.integrity import check_chain_of_copy

    try:
        result = check_chain_of_copy(copy.alias)
    except DatabaseError as exc:
        return _check("audit_chain", [f"the chain could not be read: {type(exc).__name__}"])
    problems = [f"{p['text']} (link #{p.get('sequence', '?')})" for p in result["problems"]]
    if result["problem_count"] > len(result["problems"]):
        problems.append(f"{result['problem_count']} problems in all")
    want = expected["audit"]
    found_end = (result["last_sequence"], result["chain_head"])
    if found_end != (want["last_sequence"], want["chain_head"]):
        problems.append("the end of the chain differs from the backup")
    return _check(
        "audit_chain",
        problems,
        passed_detail=f"{result['checked']} link(s) checked, chain head matches the backup",
    )


def _encrypted_check(cursor) -> dict:
    samples = encrypted_samples(cursor)
    unreadable = 0
    for value in samples:
        try:
            crypto.decrypt(value)
        except crypto.DecryptionError:
            unreadable += 1
    problems = [f"{unreadable} of {len(samples)} value(s) cannot be read"] if unreadable else []
    detail = f"{len(samples)} value(s) read" if samples else "Nothing encrypted is stored yet"
    return _check("encrypted_data", problems, passed_detail=detail)


def _documents_check(copy: RestoredCopy, expected: dict, found: dict) -> dict:
    problems = []
    for document in found["documents"].values():
        path = copy.documents / document["file"]
        if not path.is_file():
            problems.append(f"{document['file']} missing")
        elif _sha256(path) != document["sha256"] or path.stat().st_size != document["bytes"]:
            problems.append(f"{document['file']} changed")
    for relative, want in expected.get("files", {}).items():
        path = copy.documents / relative
        if not path.is_file():
            problems.append(f"{relative} missing from the backup copy")
        elif _sha256(path) != want["sha256"]:
            problems.append(f"{relative} changed in the backup copy")
    count = len(found["documents"])
    return _check(
        "documents",
        sorted(set(problems)),
        passed_detail=f"{count} document(s) checked against their fingerprints",
    )


def verify(backup: Backup, copy: RestoredCopy) -> list[dict]:
    """Every check of a restored copy against what the backup recorded."""
    expected = backup.manifest
    checks = [_check("restore", [copy.error] if copy.error else [])]
    try:
        database = pg_tools.database_settings()
        with pg_tools.connect(database, name=copy.database) as conn, conn.cursor() as cursor:
            found = describe(cursor)
            encrypted = _encrypted_check(cursor)
    except psycopg.Error as exc:  # restored only in part: nothing more can be compared
        unreadable = f"the restored copy could not be read: {scrub(str(exc))[:200]}"
        return [*checks, _check("tables", [unreadable])]
    tables = len(found["tables"])
    want_migrations, got_migrations = expected["migrations"], found["migrations"]
    checks += [
        _check(
            "migrations",
            [f"{m} missing" for m in want_migrations if m not in got_migrations]
            + [f"{m} not in the backup" for m in got_migrations if m not in want_migrations],
            passed_detail=f"{len(got_migrations)} migration(s)",
        ),
        _check(
            "tables",
            _table_problems(expected["tables"], found["tables"]),
            passed_detail=f"{tables} table(s), "
            f"{sum(t['rows'] for t in found['tables'].values())} row(s)",
        ),
        _check(
            "constraints",
            _compare(expected["constraints"], found["constraints"], what="rule")
            + [f"rule {n} not enforced" for n, c in found["constraints"].items() if not c["valid"]],
            passed_detail=f"{len(found['constraints'])} rule(s)",
        ),
        _check(
            "triggers",
            _compare(expected["triggers"], found["triggers"], what="trigger"),
            passed_detail=f"{len(found['triggers'])} trigger(s)",
        ),
        _check(
            "indexes",
            _compare(expected["indexes"], found["indexes"], what="index"),
            passed_detail=f"{len(found['indexes'])} index(es)",
        ),
        _check(
            "extensions",
            [f"{e} missing" for e in expected["extensions"] if e not in found["extensions"]],
            passed_detail=", ".join(sorted(found["extensions"])),
        ),
        _check(
            "sequences",
            _compare(expected["sequences"], found["sequences"], what="counter"),
            passed_detail=f"{len(found['sequences'])} counter(s)",
        ),
        _audit_chain_check(copy, expected),
        _check(
            "audit_relationships",
            _audit_relationship_problems(expected, found),
            passed_detail=f"{found['audit']['events']} audit record(s), "
            f"{found['audit']['links']} chain link(s)",
        ),
        encrypted,
        _documents_check(copy, expected, found),
    ]
    return checks


# --- Restore drill ---------------------------------------------------------------------------


def run_restore_drill(*, backup: Backup, trigger: str, actor=None, request=None) -> RestoreDrill:
    """Restore ``backup`` into a separate copy, check everything, remove the copy, keep the
    result as evidence."""
    _require_local()
    started_at = timezone.now()
    path = backup_folder() / backup.name / DUMP_FILE
    file_ok = path.is_file() and _sha256(path) == backup.dump_sha256
    file_check = _check(
        "backup_file",
        [] if file_ok else [f"{path.name} is missing or changed since the backup was made"],
        passed_detail=f"{backup.dump_bytes} bytes, fingerprint matches",
    )
    database, seconds = "", 0.0
    if file_ok:
        with restored_copy(backup) as copy:
            checks = [file_check, *verify(backup, copy)]
            database, seconds = copy.database, copy.seconds
    else:
        checks = [file_check]
    problems = sum(1 for check in checks if not check["passed"])
    age = max(timedelta(0), started_at - backup.created_at)
    drill = RestoreDrill.objects.create(
        backup=backup,
        started_at=started_at,
        trigger=trigger,
        requested_by_id=getattr(actor, "pk", None),
        outcome=RestoreDrill.Outcome.FAILED if problems else RestoreDrill.Outcome.PASSED,
        restore_seconds=seconds,
        backup_age_minutes=int(age.total_seconds() // 60),
        restored_database=database,
        checks=checks,
        problem_count=problems,
    )
    record_audit_event(
        action=AuditAction.RESTORE_DRILL_COMPLETED,
        resource_type="restore_drill",
        resource_id=drill.pk,
        actor=actor,
        request=request,
        outcome=AuditEvent.Outcome.FAILURE if problems else AuditEvent.Outcome.SUCCESS,
        metadata={
            "backup": backup.name,
            "checks_failed": [c["key"] for c in checks if not c["passed"]],
            "restore_seconds": seconds,
        },
    )
    if problems:
        logger.error(
            "restore_drill_failed", extra={"drill_id": str(drill.pk), "problems": problems}
        )
    return drill


def recovery_status() -> dict:
    """The latest backup and drills, and whether a drill is overdue."""
    interval = settings.HIMS_RESTORE_DRILL_INTERVAL_DAYS
    last_passed = RestoreDrill.objects.filter(outcome=RestoreDrill.Outcome.PASSED).first()
    overdue = last_passed is None or last_passed.finished_at < timezone.now() - timedelta(
        days=interval
    )
    tools, tools_problem = "", ""
    try:
        tools = pg_tools.find_tools().source
    except RecoveryError as exc:
        tools_problem = exc.detail
    return {
        "can_run_here": can_run_here(),
        "backup_folder": str(backup_folder()),
        "tools": tools,
        "tools_problem": tools_problem,
        "drill_interval_days": interval,
        "drill_overdue": overdue,
        "last_backup": Backup.objects.first(),
        "last_drill": RestoreDrill.objects.first(),
        "last_passed_drill": last_passed,
    }
