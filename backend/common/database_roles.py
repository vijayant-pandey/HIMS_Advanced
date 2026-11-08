"""Separate database users per job (spec 13.2 least privilege, 17.2, 30.5 "separate credentials
per application role: runtime, migration, read-only reporting, support/break-glass"; ADR-013;
HIMS-OPS-007). See docs/workflows/database-users.md.

* **migration** (owner): ``migrate`` and the setup command. Owns and changes every table.
* **app** (runtime): the API, admin console and workers. Reads and writes rows; never changes,
  deletes or empties the audit log and other evidence, never changes the schema.
* **read-only**: reports. Reads rows, except credentials (password hashes, two-factor secrets,
  sessions).
* **break-glass**: emergencies, after approval. Cannot sign in until switched on for a limited
  time; then has the app's rights, never the owner's.

Which tables are evidence is read from the database itself: every table protected by an
append-only trigger (audit log, chain, integrity checks, backups, restore drills). Which columns
are credentials comes from the data dictionary (level "Secret"). Grants are re-applied after
every ``migrate``, so new tables are covered without anyone remembering to.
"""

import re
from dataclasses import dataclass

from django.conf import settings
from psycopg import sql

# Trigger functions that make a table append-only (audit 0002 and 0003).
APPEND_ONLY_FUNCTIONS = ("audit_events_reject_mutation", "audit_reject_mutation")
# Tables outside the data dictionary whose every column is a credential.
SECRET_TABLES = frozenset({"django_session"})
APP_TABLE_RIGHTS = ("SELECT", "INSERT", "UPDATE", "DELETE")
EVIDENCE_RIGHTS = ("SELECT", "INSERT")


@dataclass(frozen=True)
class RoleNames:
    app: str
    readonly: str
    breakglass: str


def _role_base() -> str:
    deployment = re.sub(r"[^a-z0-9]+", "_", settings.HIMS_DEPLOYMENT_ID.lower()).strip("_")
    return f"hims_{deployment}"[:50]


def role_names() -> RoleNames:
    """One set of users per hospital deployment (both local hospitals can share a server)."""
    base = _role_base()
    return RoleNames(
        app=settings.HIMS_DB_APP_ROLE or f"{base}_app",
        readonly=settings.HIMS_DB_READONLY_ROLE or f"{base}_readonly",
        breakglass=settings.HIMS_DB_BREAKGLASS_ROLE or f"{base}_breakglass",
    )


def _one(cursor, query, params=None):
    cursor.execute(query, params)
    row = cursor.fetchone()
    return row[0] if row else None


def _all(cursor, query, params=None) -> list[tuple]:
    cursor.execute(query, params)
    return cursor.fetchall()


def role_exists(cursor, role: str) -> bool:
    return bool(_one(cursor, "SELECT 1 FROM pg_roles WHERE rolname = %s", [role]))


def tables(cursor) -> list[str]:
    return [
        t
        for (t,) in _all(
            cursor, "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1"
        )
    ]


def evidence_tables(cursor) -> list[str]:
    """Tables an append-only trigger protects: the app may add rows, never change them."""
    return [
        name
        for (name,) in _all(
            cursor,
            "SELECT DISTINCT c.relname FROM pg_trigger t "
            "JOIN pg_class c ON c.oid = t.tgrelid JOIN pg_proc p ON p.oid = t.tgfoid "
            "WHERE NOT t.tgisinternal AND p.proname = ANY(%s) ORDER BY 1",
            [list(APPEND_ONLY_FUNCTIONS)],
        )
    ]


def secret_columns() -> dict[str, set[str]]:
    """Columns the data dictionary classifies as Secret, by table."""
    from common.datadict import catalog
    from common.datadict.generator import classify, domain_models

    found: dict[str, set[str]] = {}
    for _, models in domain_models():
        for model in models:
            table = model._meta.db_table
            for field in model._meta.concrete_fields:
                if classify(table, field)[0] == catalog.SECRET:
                    found.setdefault(table, set()).add(field.column)
    return found


def _columns(cursor, table: str) -> list[str]:
    return [
        c
        for (c,) in _all(
            cursor,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
            [table],
        )
    ]


def _raw(cursor):
    """The psycopg cursor behind Django's wrapper (composed SQL goes to it directly)."""
    return getattr(cursor, "cursor", cursor)


def _rights(names) -> sql.Composable:
    return sql.SQL(", ").join(sql.SQL(name) for name in names)


def apply_grants(cursor, names: RoleNames | None = None) -> dict:
    """Give each user exactly its rights on every table of this database (idempotent). Run as
    the owner (migration user). Returns what was granted, for the audit record."""
    cursor = _raw(cursor)
    names = names or role_names()
    if not role_exists(cursor, names.app):
        return {"applied": False}
    database = _one(cursor, "SELECT current_database()")
    owner = _one(cursor, "SELECT current_user")
    readers = [names.app, names.readonly] if role_exists(cursor, names.readonly) else [names.app]
    who = sql.SQL(", ").join(sql.Identifier(r) for r in readers)
    cursor.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database), who)
    )
    cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(who))
    evidence = set(evidence_tables(cursor))
    secrets = secret_columns()
    app = sql.Identifier(names.app)
    for table in tables(cursor):
        name = sql.Identifier(table)
        cursor.execute(sql.SQL("REVOKE ALL ON TABLE {} FROM {}").format(name, who))
        rights = EVIDENCE_RIGHTS if table in evidence else APP_TABLE_RIGHTS
        cursor.execute(sql.SQL("GRANT {} ON TABLE {} TO {}").format(_rights(rights), name, app))
        if names.readonly not in readers:
            continue
        reader = sql.Identifier(names.readonly)
        columns = _columns(cursor, table)
        cursor.execute(
            sql.SQL("REVOKE SELECT ({}) ON TABLE {} FROM {}").format(
                sql.SQL(", ").join(sql.Identifier(c) for c in columns), name, reader
            )
        )
        hidden = set(columns) if table in SECRET_TABLES else secrets.get(table, set())
        visible = [c for c in columns if c not in hidden]
        if not hidden:
            cursor.execute(sql.SQL("GRANT SELECT ON TABLE {} TO {}").format(name, reader))
        elif visible:
            cursor.execute(
                sql.SQL("GRANT SELECT ({}) ON TABLE {} TO {}").format(
                    sql.SQL(", ").join(sql.Identifier(c) for c in visible), name, reader
                )
            )
    cursor.execute(
        sql.SQL("GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {}").format(app)
    )
    # Tables created later by the owner work for the app at once; ``migrate`` then re-applies
    # these grants, which also protects new evidence tables and hides new credential columns.
    cursor.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
        ).format(sql.Identifier(owner), app)
    )
    cursor.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
            "GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {}"
        ).format(sql.Identifier(owner), app)
    )
    return {"applied": True, "tables": len(tables(cursor)), "evidence_tables": sorted(evidence)}


def create_or_update_roles(cursor, names: RoleNames, *, app_password: str, readonly_password: str):
    """Create the users (or set new passwords). Passwords are sent as SCRAM verifiers, so the
    plain password never appears in a database log."""
    cursor = _raw(cursor)
    conn = cursor.connection
    for role, password in ((names.app, app_password), (names.readonly, readonly_password)):
        verifier = conn.pgconn.encrypt_password(
            password.encode(), role.encode(), b"scram-sha-256"
        ).decode()
        verb = "ALTER" if role_exists(cursor, role) else "CREATE"
        cursor.execute(
            sql.SQL(
                "{} ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS "
                "PASSWORD {}"
            ).format(sql.SQL(verb), sql.Identifier(role), sql.Literal(verifier))
        )
    breakglass = sql.Identifier(names.breakglass)
    if not role_exists(cursor, names.breakglass):
        cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(breakglass))
    cursor.execute(
        sql.SQL(
            "ALTER ROLE {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
        ).format(breakglass)
    )
    cursor.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(names.app), breakglass))


# --- Checks ----------------------------------------------------------------------------------

CHECK_LABELS = {
    "separate_users": "The app connects as its own user, not as the owner",
    "app_not_owner": "The app's user owns no table and cannot change the schema",
    "app_no_admin_rights": "The app's user cannot create users or databases",
    "evidence_protected": "The app cannot change, delete or empty the audit log and other evidence",
    "app_cannot_empty_tables": "The app cannot empty any table in one go (TRUNCATE)",
    "readonly_reads_only": "The read-only user can only read, and never credentials",
    "breakglass_off": "The break-glass user exists and is switched off",
}


def _check(key: str, problems: list[str], passed_detail: str = "") -> dict:
    return {
        "key": key,
        "label": CHECK_LABELS[key],
        "passed": not problems,
        "detail": "; ".join(problems[:10]) if problems else passed_detail,
    }


def _rights_held(cursor, role: str, rights: tuple[str, ...]) -> list[tuple[str, str]]:
    """(table, right) pairs ``role`` holds among ``rights``, in one query."""
    return _all(
        cursor,
        "SELECT t.tablename, r FROM pg_tables t, unnest(%s::text[]) AS r "
        "WHERE t.schemaname = 'public' "
        "AND has_table_privilege(%s, format('public.%%I', t.tablename), r) ORDER BY 1, 2",
        [list(rights), role],
    )


def _secret_columns_readable(cursor, role: str) -> list[str]:
    readable = []
    for table, columns in sorted(secret_columns().items()):
        for column in sorted(columns):
            if _one(
                cursor,
                "SELECT has_column_privilege(%s, format('public.%%I', %s::text), %s, 'SELECT')",
                [role, table, column],
            ):
                readable.append(f"{table}.{column}")
    return readable


def inspect(cursor, names: RoleNames | None = None) -> dict:
    """How database access is separated, checked from the database itself."""
    names = names or role_names()
    current = _one(cursor, "SELECT current_user")
    all_tables = tables(cursor)
    owners = sorted(
        o
        for (o,) in _all(
            cursor, "SELECT DISTINCT tableowner FROM pg_tables WHERE schemaname = 'public'"
        )
    )
    app_exists = role_exists(cursor, names.app)
    problems = []
    if not app_exists:
        problems.append("the app's own database user has not been set up yet")
    elif current != names.app:
        problems.append(f"the app connects as {current}, not as {names.app}")
    checks = [
        _check(
            "separate_users",
            problems,
            passed_detail=f"app connects as {current}; tables owned by {', '.join(owners)}",
        )
    ]
    result = {"set_up": app_exists, "current_user": current, "names": names, "checks": checks}
    if not app_exists:
        return result

    flags = _all(
        cursor,
        "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls FROM pg_roles "
        "WHERE rolname = %s",
        [names.app],
    )[0]
    owned = [
        t
        for (t,) in _all(
            cursor,
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tableowner = %s",
            [names.app],
        )
    ]
    can_create = _one(cursor, "SELECT has_schema_privilege(%s, 'public', 'CREATE')", [names.app])
    checks.append(
        _check(
            "app_not_owner",
            [f"owns {t}" for t in owned] + (["may create tables"] if can_create else []),
            passed_detail=f"{len(all_tables)} table(s), none owned by the app",
        )
    )
    labels = ("superuser", "may create users", "may create databases", "bypasses row security")
    checks.append(
        _check(
            "app_no_admin_rights",
            [label for flag, label in zip(flags, labels, strict=True) if flag],
            passed_detail="none of: superuser, create users, create databases",
        )
    )
    evidence = evidence_tables(cursor)
    held = _rights_held(cursor, names.app, ("UPDATE", "DELETE", "TRUNCATE"))
    checks.append(
        _check(
            "evidence_protected",
            [f"{right} on {table}" for table, right in held if table in evidence]
            + ([] if evidence else ["no append-only tables found"]),
            passed_detail=f"add-only: {', '.join(evidence)}",
        )
    )
    checks.append(
        _check(
            "app_cannot_empty_tables",
            [table for table, right in held if right == "TRUNCATE"],
            passed_detail=f"{len(all_tables)} table(s)",
        )
    )
    if role_exists(cursor, names.readonly):
        writes = _rights_held(cursor, names.readonly, ("INSERT", "UPDATE", "DELETE", "TRUNCATE"))
        reads_secret = [
            t for t, _ in _rights_held(cursor, names.readonly, ("SELECT",)) if t in SECRET_TABLES
        ]
        readonly_problems = (
            [f"{right} on {table}" for table, right in writes]
            + [f"reads {t}" for t in reads_secret]
            + [f"reads {c}" for c in _secret_columns_readable(cursor, names.readonly)]
        )
    else:
        readonly_problems = ["the read-only user does not exist"]
    checks.append(
        _check(
            "readonly_reads_only",
            readonly_problems,
            passed_detail="reads every table except credential columns",
        )
    )
    breakglass = _all(
        cursor, "SELECT rolcanlogin FROM pg_roles WHERE rolname = %s", [names.breakglass]
    )
    checks.append(
        _check(
            "breakglass_off",
            ["does not exist"]
            if not breakglass
            else (["is switched on"] if breakglass[0][0] else []),
            passed_detail="cannot sign in until switched on for an emergency",
        )
    )
    return result
