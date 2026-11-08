"""Backups and restore drills (HIMS-OPS-009; spec 13.5 "a database restore recovers records but
fails to restore required audit relationships", 17.3, 27.1). Synthetic data only.

The drill tests really run pg_dump and pg_restore against the test database (committed data,
hence ``transaction=True``). Without the tools they are skipped on a developer PC, never in CI.
"""

import hashlib
import os
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import override_settings
from django.utils import timezone

from apps.audit.integrity import seal_pending_events
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.identity.models import MfaDevice
from apps.recovery import pg_tools
from apps.recovery.inventory import same_rule
from apps.recovery.models import Backup, RestoreDrill
from apps.recovery.pg_tools import RecoveryError
from apps.recovery.services import (
    CHECK_LABELS,
    DOCUMENTS_FOLDER,
    DUMP_FILE,
    backup_folder,
    create_backup,
    restored_copy,
    run_restore_drill,
    verify,
)
from apps.staff.models import StaffCredential, StaffMember
from common import crypto

API = "/api/v1"
PDF = b"%PDF-1.4\n% synthetic restore drill document\n%%EOF\n"


def _tools():
    try:
        return pg_tools.find_tools()
    except RecoveryError as error:
        if os.environ.get("CI"):
            raise  # CI must run the real drill (HIMS_PG_DOCKER_CONTAINER)
        pytest.skip(error.detail)


@pytest.fixture
def hospital(organization, make_user, system_roles, client_for, settings, tmp_path):
    """A hospital with records worth restoring: someone using two-factor (an encrypted secret), a
    member of staff with an uploaded licence copy, and sealed audit records. Its own empty
    document and backup folders (other tests leave files in the shared test folder)."""
    _tools()
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.HIMS_BACKUP_DIR = tmp_path / "backups"
    admin = make_user(role=system_roles["organization-administrator"])
    MfaDevice.objects.create(
        user=make_user(),
        secret_encrypted=crypto.encrypt("JBSWY3DPEHPK3PXP"),
        confirmed_at=timezone.now(),
    )
    nurse = StaffMember.objects.create(
        organization=organization,
        employee_number="EMP-DRILL-1",
        given_name="Asha",
        family_name="Drill",
        staff_type="nurse",
        joined_on="2026-01-05",
    )
    licence = StaffCredential.objects.create(
        organization=organization,
        staff=nurse,
        credential_type="nursing_registration",
        registration_number="KNC-DRILL-1",
        issuing_authority="Karnataka Nursing Council",
        jurisdiction="IN-KA",
        expires_at="2027-01-01",
    )
    client = client_for(admin)
    upload = client.post(
        f"{API}/staff/{nurse.pk}/documents/",
        {"file": SimpleUploadedFile("licence.pdf", PDF), "credential": str(licence.pk)},
        format="multipart",
    )
    assert upload.status_code == 201, upload.json()
    seal_pending_events()
    return {"admin": admin, "client": client}


def _database_exists(name: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", [name])
        return cursor.fetchone() is not None


def _passed(checks) -> set[str]:
    return {check["key"] for check in checks if check["passed"]}


def _failed(checks) -> set[str]:
    return {check["key"] for check in checks if not check["passed"]}


@pytest.mark.django_db(transaction=True)
def test_backup_then_restore_drill_proves_records_audit_and_documents_came_back(hospital):
    client = hospital["client"]
    made = client.post(f"{API}/backups/")
    assert made.status_code == 201, made.json()
    backup = Backup.objects.get(pk=made.json()["id"])
    folder = backup_folder() / backup.name
    assert (folder / DUMP_FILE).is_file() and (folder / "manifest.json").is_file()
    assert backup.documents == 1 and len(list((folder / DOCUMENTS_FOLDER).rglob("*.pdf"))) == 1

    ran = client.post(f"{API}/restore-drills/", {"backup": str(backup.pk)}, format="json")
    assert ran.status_code == 201, ran.json()
    drill = ran.json()
    assert drill["outcome"] == "passed", [c for c in drill["checks"] if not c["passed"]]
    assert {c["key"] for c in drill["checks"]} == set(CHECK_LABELS)
    by_key = {c["key"]: c for c in drill["checks"]}
    assert by_key["documents"]["detail"] == "1 document(s) checked against their fingerprints"
    assert by_key["encrypted_data"]["detail"] == "1 value(s) read"
    assert "chain head matches the backup" in by_key["audit_chain"]["detail"]
    # The copy was separate and is gone; both steps are in the audit log.
    assert drill["restored_database"] != connection.settings_dict["NAME"]
    assert not _database_exists(drill["restored_database"])
    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {AuditAction.BACKUP_CREATED, AuditAction.RESTORE_DRILL_COMPLETED} <= actions
    status = client.get(f"{API}/backups/status/").json()
    assert status["drill_overdue"] is False and status["last_passed_drill"]["id"] == drill["id"]


@pytest.mark.django_db(transaction=True)
def test_restore_that_loses_audit_relationships_is_caught(hospital):
    """Spec 13.5: the records came back, but the audit chain links did not and the audit log
    lost its protection. The drill must fail and say so."""
    backup = create_backup(actor=hospital["admin"])
    with restored_copy(backup) as copy:
        with pg_tools.connect(pg_tools.database_settings(), name=copy.database) as damaged:
            damaged.execute("TRUNCATE audit_chain_entries")
            damaged.execute("DROP TRIGGER audit_events_append_only ON audit_events")
        checks = verify(backup, copy)
    failed = _failed(checks)
    assert {"tables", "triggers", "audit_chain", "audit_relationships"} <= failed
    assert {"restore", "migrations", "documents", "encrypted_data"} <= _passed(checks)
    relationships = next(c for c in checks if c["key"] == "audit_relationships")
    assert "audit_events.audit_events_append_only no longer protects" in relationships["detail"]


@pytest.mark.django_db(transaction=True)
def test_a_document_missing_from_the_backup_fails_the_drill(hospital):
    backup = create_backup(actor=hospital["admin"])
    for document in (backup_folder() / backup.name / DOCUMENTS_FOLDER).rglob("*.pdf"):
        document.unlink()
    drill = run_restore_drill(backup=backup, trigger=RestoreDrill.Trigger.COMMAND)
    assert drill.outcome == RestoreDrill.Outcome.FAILED
    assert _failed(drill.checks) == {"documents"}
    assert "missing" in next(c for c in drill.checks if c["key"] == "documents")["detail"]


@pytest.mark.django_db(transaction=True)
def test_a_changed_backup_file_is_refused_before_restoring(hospital):
    backup = create_backup(actor=hospital["admin"])
    dump = backup_folder() / backup.name / DUMP_FILE
    dump.write_bytes(dump.read_bytes()[:-10] + b"0123456789")
    drill = run_restore_drill(backup=backup, trigger=RestoreDrill.Trigger.COMMAND)
    assert drill.outcome == RestoreDrill.Outcome.FAILED
    assert [c["key"] for c in drill.checks] == ["backup_file"] and drill.restored_database == ""


@pytest.mark.django_db(transaction=True)
def test_a_backup_postgres_cannot_restore_is_recorded_as_failed(hospital):
    good = create_backup(actor=hospital["admin"])
    broken_folder = backup_folder() / "synthetic-broken-backup"
    broken_folder.mkdir()
    (broken_folder / DUMP_FILE).write_bytes(b"not a PostgreSQL backup")
    broken = Backup.objects.create(
        name="synthetic-broken-backup",
        database_name=good.database_name,
        environment=good.environment,
        dump_bytes=23,
        dump_sha256=hashlib.sha256(b"not a PostgreSQL backup").hexdigest(),
        tables=good.tables,
        rows=good.rows,
        documents=0,
        documents_bytes=0,
        seconds=0,
        manifest=good.manifest,
    )
    drill = run_restore_drill(backup=broken, trigger=RestoreDrill.Trigger.COMMAND)
    assert drill.outcome == RestoreDrill.Outcome.FAILED
    assert {"restore", "tables"} <= _failed(drill.checks)
    assert "pg_restore failed" in next(c for c in drill.checks if c["key"] == "restore")["detail"]
    assert not _database_exists(drill.restored_database)


# --- Rules that need no PostgreSQL tools ------------------------------------------------------


@pytest.fixture
def auditor(make_user, system_roles):
    return make_user(role=system_roles["auditor"])


@pytest.fixture
def admin(make_user, system_roles):
    return make_user(role=system_roles["organization-administrator"])


@pytest.mark.django_db
def test_only_on_a_developer_pc(client_for, admin):
    with override_settings(HIMS_ENVIRONMENT="staging"):
        refused = client_for(admin).post(f"{API}/backups/")
        assert refused.status_code == 409
        assert "cloud database service" in refused.json()["detail"]
        assert client_for(admin).get(f"{API}/backups/status/").json()["can_run_here"] is False
    assert not Backup.objects.exists()


@pytest.mark.django_db
def test_auditors_see_the_evidence_but_cannot_make_backups_or_drills(client_for, auditor):
    client = client_for(auditor)
    assert client.get(f"{API}/backups/").status_code == 200
    assert client.get(f"{API}/restore-drills/").status_code == 200
    status = client.get(f"{API}/backups/status/").json()
    assert status["drill_overdue"] is True and status["last_backup"] is None
    assert client.post(f"{API}/backups/").status_code == 403
    body = {"backup": "00000000-0000-0000-0000-000000000000"}
    assert client.post(f"{API}/restore-drills/", body, format="json").status_code == 403


@pytest.mark.django_db
def test_people_without_the_permission_see_nothing(client_for, make_user, system_roles):
    client = client_for(make_user(role=system_roles["basic-staff"]))
    assert client.get(f"{API}/backups/status/").status_code == 403
    assert client.get(f"{API}/restore-drills/").status_code == 403


@pytest.mark.django_db
def test_evidence_cannot_be_changed_or_removed(admin):
    backup = Backup.objects.create(
        name="synthetic-evidence",
        database_name="x",
        environment="test",
        dump_bytes=1,
        dump_sha256="0" * 64,
        tables=1,
        rows=1,
        documents=0,
        documents_bytes=0,
        seconds=0,
        manifest={},
    )
    with pytest.raises(RuntimeError):
        backup.save()
    with pytest.raises(Exception, match="append-only"), connection.cursor() as cursor:
        cursor.execute("UPDATE recovery_backups SET name = 'changed'")


def test_the_password_never_goes_on_the_command_line():
    database = {"NAME": "hims", "USER": "hims", "PASSWORD": "Synthetic-Db-Passw0rd-2005"}
    for tools in (
        pg_tools.Tools(("docker", "exec", "-i", "-e", "PGPASSWORD", "db1"), "container", True),
        pg_tools.Tools((str(Path("C:/pg/bin")),), "HIMS_PG_BIN_DIR", False),
    ):
        command = tools.command(
            "pg_dump", *pg_tools._connection_args(tools, database, database["NAME"])
        )
        assert database["PASSWORD"] not in " ".join(command)
        assert "--dbname=hims" in command and "--username=hims" in command


@override_settings(HIMS_PG_BIN_DIR="C:/no/such/folder", HIMS_PG_DOCKER_CONTAINER="")
def test_a_wrong_tools_folder_is_explained():
    with pytest.raises(RecoveryError, match="HIMS_PG_BIN_DIR"):
        pg_tools.find_tools()


def test_rules_compare_by_meaning_not_by_how_postgres_prints_casts():
    live = (
        "EXCLUDE USING gist (staff_id WITH =) WHERE (((status)::text = ANY "
        "((ARRAY['requested'::character varying, 'approved'::character varying])::text[])))"
    )
    restored = (
        "EXCLUDE USING gist (staff_id WITH =) WHERE (((status)::text = ANY "
        "(ARRAY[('requested'::character varying)::text, ('approved'::character varying)::text])))"
    )
    assert same_rule(live) == same_rule(restored)
    assert same_rule(live) != same_rule(live.replace("'approved'", "'rejected'"))
    assert same_rule(live) != same_rule(live.replace("WITH =", "WITH &&"))
