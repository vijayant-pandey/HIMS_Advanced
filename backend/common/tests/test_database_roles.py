"""Separate database users (HIMS-OPS-007; spec 13.2, 17.2, 30.5; ADR-013). Synthetic data.

The users are created inside each test's transaction (so they disappear afterwards) and the
tests act as them with ``SET ROLE``: PostgreSQL then checks every statement against that user's
rights, exactly as for a real connection.
"""

import os
import subprocess
import sys
from contextlib import contextmanager
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction
from django.test import override_settings

from apps.audit.apps import _reapply_database_grants
from apps.audit.integrity import run_integrity_check, seal_pending_events
from apps.audit.models import AuditEvent, AuditIntegrityCheck
from apps.audit.services import AuditAction
from common import database_roles
from common.database_roles import RoleNames, apply_grants, create_or_update_roles, inspect

API = "/api/v1"
BACKEND = Path(__file__).resolve().parents[2]
NAMES = RoleNames(app="hims_t_app", readonly="hims_t_readonly", breakglass="hims_t_breakglass")
AS_SETTINGS = override_settings(
    HIMS_DB_APP_ROLE=NAMES.app,
    HIMS_DB_READONLY_ROLE=NAMES.readonly,
    HIMS_DB_BREAKGLASS_ROLE=NAMES.breakglass,
)


@pytest.fixture
def users(db):
    with connection.cursor() as cursor:
        create_or_update_roles(
            cursor,
            NAMES,
            app_password="Synthetic-App-Passw0rd-3001",
            readonly_password="Synthetic-Read-Passw0rd-3002",
        )
        apply_grants(cursor, NAMES)
    return NAMES


@contextmanager
def acting_as(role: str):
    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{role}"')
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")


def refused(statement: str) -> bool:
    """True when PostgreSQL refuses the statement for the current user."""
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(statement)
    except DatabaseError as error:
        return "permission denied" in str(error) or "must be owner" in str(error)
    return False


@pytest.mark.django_db
def test_the_app_user_cannot_change_delete_or_empty_the_audit_log(users, make_user):
    make_user()  # an audit-worthy change exists
    with acting_as(users.app):
        AuditEvent.objects.create(action=AuditAction.ACCESS_DENIED, resource_type="api")
        assert refused("UPDATE audit_events SET reason = 'changed'")
        assert refused("DELETE FROM audit_events")
        assert refused("TRUNCATE audit_events")
        assert refused("TRUNCATE audit_chain_entries")
        assert refused("UPDATE recovery_restore_drills SET problem_count = 0")
        assert refused("ALTER TABLE audit_events DISABLE TRIGGER ALL")
        assert refused("DROP TRIGGER audit_events_append_only ON audit_events")
        assert refused("DROP TABLE audit_events")
        assert refused("CREATE TABLE hims_t_new (id int)")
        assert refused("TRUNCATE users")  # nor any other table


@pytest.mark.django_db
def test_the_app_still_does_all_its_work_as_its_own_user(
    users, client_for, make_user, system_roles, facility_a
):
    """Signing in, changing records, the outbox and the audit tamper check all work with the
    app's limited rights (nothing in normal work needs to change or delete evidence)."""
    admin = make_user(role=system_roles["organization-administrator"])
    with acting_as(users.app):
        client = client_for(admin)
        assert client.get(f"{API}/auth/me/").status_code == 200
        changed = client.patch(
            f"{API}/facilities/{facility_a.pk}/",
            {"version": facility_a.version, "city": "Mysuru"},
            format="json",
        )
        assert changed.status_code == 200, changed.json()
        seal_pending_events()
        check = run_integrity_check(trigger=AuditIntegrityCheck.Trigger.COMMAND)
        assert check.outcome == AuditIntegrityCheck.Outcome.PASSED
        assert client.get(f"{API}/audit-events/").status_code in (200, 403)
        assert client.post(f"{API}/auth/logout/").status_code in (200, 204)


@pytest.mark.django_db
def test_the_read_only_user_reads_but_never_credentials(users, make_user):
    make_user()
    with acting_as(users.readonly):
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, email, display_name FROM users")
            assert cursor.fetchall()
            cursor.execute("SELECT count(*) FROM audit_events")
        assert refused("SELECT password FROM users")
        assert refused("SELECT secret_encrypted FROM user_mfa_devices")
        assert refused("SELECT session_data FROM django_session")
        assert refused("INSERT INTO audit_events (id) VALUES (gen_random_uuid())")
        assert refused("UPDATE users SET display_name = 'x'")


@pytest.mark.django_db
def test_break_glass_is_switched_off_and_never_more_than_the_app(users):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolcanlogin, rolsuper, pg_has_role(%s, %s, 'MEMBER') FROM pg_roles "
            "WHERE rolname = %s",
            [users.breakglass, users.app, users.breakglass],
        )
        can_login, superuser, has_app_rights = cursor.fetchone()
    assert (can_login, superuser, has_app_rights) == (False, False, True)


@pytest.mark.django_db
def test_the_checks_pass_only_when_the_app_runs_as_its_own_user(users):
    with connection.cursor() as cursor:
        as_owner = inspect(cursor, users)
    assert as_owner["set_up"] is True
    assert [c["key"] for c in as_owner["checks"] if not c["passed"]] == ["separate_users"]
    with acting_as(users.app), connection.cursor() as cursor:
        as_app = inspect(cursor, users)
    assert all(c["passed"] for c in as_app["checks"]), as_app["checks"]
    assert set(database_roles.CHECK_LABELS) == {c["key"] for c in as_app["checks"]}


@pytest.mark.django_db
def test_not_set_up_yet_is_reported_plainly(db):
    missing = RoleNames(
        app="hims_t_none_app", readonly="hims_t_none_ro", breakglass="hims_t_none_bg"
    )
    with connection.cursor() as cursor:
        result = inspect(cursor, missing)
    assert result["set_up"] is False
    assert "has not been set up yet" in result["checks"][0]["detail"]


@pytest.mark.django_db
def test_new_evidence_tables_are_protected_when_migrate_reapplies_the_grants(users):
    with connection.cursor() as cursor:
        cursor.execute("CREATE TABLE hims_t_evidence (id int)")
        cursor.execute(
            "CREATE TRIGGER hims_t_evidence_append_only BEFORE UPDATE OR DELETE ON "
            "hims_t_evidence FOR EACH ROW EXECUTE FUNCTION audit_reject_mutation()"
        )
        cursor.execute("CREATE TABLE hims_t_plain (id int)")
    with AS_SETTINGS:
        _reapply_database_grants(sender=None)
    with acting_as(users.app):
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO hims_t_evidence VALUES (1)")
            cursor.execute("INSERT INTO hims_t_plain VALUES (1)")
            cursor.execute("UPDATE hims_t_plain SET id = 2")
        assert refused("UPDATE hims_t_evidence SET id = 2")
        assert refused("TRUNCATE hims_t_plain")


# --- Commands and screen ---------------------------------------------------------------------


@pytest.mark.django_db
@AS_SETTINGS
@override_settings(HIMS_MIGRATION_DATABASE_URL="")
def test_setup_writes_the_env_file_and_never_prints_a_password(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_bytes(
        b"HIMS_ENVIRONMENT=local\r\nDATABASE_URL=postgres://owner:Synthetic-Owner-Passw0rd-3003@localhost:5432/hims\r\n"
    )
    out = StringIO()
    call_command("setup_database_roles", "--write-env", "--env-file", str(env_file), stdout=out)
    text = env_file.read_bytes().decode()
    values = dict(line.split("=", 1) for line in text.split("\r\n") if "=" in line)
    assert values["HIMS_MIGRATION_DATABASE_URL"].startswith("postgres://owner:")
    assert values["DATABASE_URL"].startswith(f"postgres://{NAMES.app}:")
    assert values["HIMS_READONLY_DATABASE_URL"].startswith(f"postgres://{NAMES.readonly}:")
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")  # line endings kept
    assert (tmp_path / ".env.before-database-users").is_file()
    printed = out.getvalue()
    for url in (values["DATABASE_URL"], values["HIMS_READONLY_DATABASE_URL"]):
        password = url.split("://", 1)[1].split("@", 1)[0].split(":", 1)[1]
        assert password not in printed
    assert AuditEvent.objects.filter(action=AuditAction.DATABASE_USERS_SET_UP).exists()


@pytest.mark.django_db
@AS_SETTINGS
def test_setup_without_passwords_is_refused(monkeypatch):
    monkeypatch.delenv("HIMS_APP_DATABASE_PASSWORD", raising=False)
    with pytest.raises(CommandError, match="HIMS_APP_DATABASE_PASSWORD"):
        call_command("setup_database_roles", stdout=StringIO())


@pytest.mark.django_db
@AS_SETTINGS
def test_check_command_fails_until_the_app_runs_as_its_own_user(users):
    with pytest.raises(CommandError, match="FAILED"):
        call_command("check_database_roles", stdout=StringIO())
    out = StringIO()
    with acting_as(users.app):
        call_command("check_database_roles", stdout=out)
    assert "PASSED" in out.getvalue()


@pytest.mark.django_db
@AS_SETTINGS
def test_compliance_page_shows_database_access(users, client_for, make_user, system_roles):
    auditor = make_user(role=system_roles["auditor"])
    shown = client_for(auditor).get(f"{API}/security/database-access/").json()
    assert shown["set_up"] is True and shown["separated"] is False  # tests connect as owner
    assert shown["app_user"] == NAMES.app and len(shown["checks"]) == len(
        database_roles.CHECK_LABELS
    )
    basic = make_user(role=system_roles["basic-staff"])
    assert client_for(basic).get(f"{API}/security/database-access/").status_code == 403


def _database_user_for(command: str, settings_module: str = "config.settings.local") -> str:
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": settings_module,
        "HIMS_ENVIRONMENT": settings_module.rsplit(".", 1)[1],
        "HIMS_ENV_FILE": "no-such-env-file",
        "DATABASE_URL": "postgres://hims_t_app:x@localhost:5432/hims",
        "HIMS_MIGRATION_DATABASE_URL": "postgres://hims_t_owner:y@localhost:5432/hims",
    }
    script = (
        f"import sys; sys.argv = ['manage.py', '{command}']; import django; django.setup(); "
        "from django.conf import settings; "
        "print(settings.DATABASES['default']['USER'], settings.HIMS_OWNER_DATABASE['USER'])"
    )
    result = subprocess.run(  # noqa: S603 - fixed interpreter and script
        [sys.executable, "-c", script], cwd=BACKEND, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr[-500:]
    return result.stdout.split()[-2:]


def test_only_schema_commands_use_the_owner():
    assert _database_user_for("migrate") == ["hims_t_owner", "hims_t_owner"]
    assert _database_user_for("runserver") == ["hims_t_app", "hims_t_owner"]
    assert _database_user_for("check_database_roles") == ["hims_t_app", "hims_t_owner"]
    # The test suite creates and drops its own database, so it always uses the owner.
    assert _database_user_for("pytest", "config.settings.test") == ["hims_t_owner", "hims_t_owner"]
