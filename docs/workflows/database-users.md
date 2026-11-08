# Separate database users

**Ticket:** HIMS-OPS-007 · **Spec:** 13.2 (least privilege), 13.4 (audit log protected), 17.2
("restrict production shell and database access", "controlled database migration jobs"), 30.5
("separate credentials per application role: runtime, migration, read-only reporting,
support/break-glass"). Decisions: [ADR-013](../decisions/ADR-013-audit-log-storage.md),
[ADR-026](../decisions/ADR-026-separate-database-users.md).

## In one paragraph

HIMS talks to its database with **its own limited user**. That user can read and write records,
but it cannot change the database's structure, and it can never change, delete or empty the
audit log and other evidence, not even if someone took over the app. Only the separate **owner**
(used by `migrate`) can. A **read-only** user exists for reports and never sees passwords,
two-factor secrets or sessions. A **break-glass** user exists for emergencies and is switched off.

## The four users

| User | Name (per hospital) | Used by | Can | Cannot |
|---|---|---|---|---|
| Owner (migration) | the user you set up PostgreSQL with | `migrate`, `setup_database_roles`, backups and restore drills, the test suite | Everything in this database | (it is the owner) |
| App (runtime) | `hims_<hospital>_app`, e.g. `hims_local_dev_app` | The web app, admin console, background workers | Read and write records; **add** audit records and other evidence | Change, delete or empty (`TRUNCATE`) the audit log, its chain, integrity checks, backups or restore drills; empty any table; create, change or drop tables or triggers; create users or databases |
| Read-only | `hims_<hospital>_readonly` | Reports (later), investigations | Read every table | Write anything; read password hashes, two-factor secrets, backup-code hashes, session keys or unsent messages |
| Break-glass | `hims_<hospital>_breakglass` | Emergencies, after approval | Nothing until switched on; then the app's rights | Ever more than the app (it is never the owner) |

**Which tables are evidence** is read from the database itself: every table guarded by an
append-only trigger (`audit_events`, `audit_chain_entries`, `audit_integrity_checks`,
`recovery_backups`, `recovery_restore_drills`, and any new one). **Which columns are credentials**
comes from the [data dictionary](../architecture/data-architecture/data-dictionary.md) (level
"Secret"). After every `migrate` the rights are re-applied automatically, so new tables are covered
without anyone remembering to.

## Set it up on your PC (Windows, CMD), once per hospital

Stop HIMS first (close the launcher window).

```
cd C:\Users\vpand\OneDrive\Desktop\HIMS\backend
.venv\Scripts\activate.bat
```

**India:**
```
set HIMS_ENV_FILE=
python manage.py setup_database_roles --write-env
python manage.py check_database_roles
```

**US:**
```
set HIMS_ENV_FILE=.env.us
python manage.py setup_database_roles --write-env
python manage.py check_database_roles
set HIMS_ENV_FILE=
```

What `--write-env` does, for the hospital's env file (`.env` or `.env.us`):

1. makes two new random passwords (never printed);
2. creates the app, read-only and break-glass users and gives each exactly its rights;
3. keeps a copy of the old file as `.env.before-database-users` (or `.env.us.before-database-users`);
4. moves your current `DATABASE_URL` (the owner) to `HIMS_MIGRATION_DATABASE_URL`, sets
   `DATABASE_URL` to the app's own user, and adds `HIMS_READONLY_DATABASE_URL`.

`check_database_roles` should end with `PASSED: database access is separated.` Then start HIMS
as usual. On the **Compliance** page → **Database access** every check shows **OK**.

Nothing else changes for you: `python manage.py migrate` uses the owner automatically, and so do
backups, restore drills, the test suite and the browser tests.

**To undo** (if something goes wrong): stop HIMS, delete `.env` and rename
`.env.before-database-users` back to `.env` (same for `.env.us`). The users stay in PostgreSQL but
are no longer used.

**To change the passwords** later: run `setup_database_roles --write-env` again.

## Hosted environments (with AWS, later)

- The secret manager holds three credentials per hospital: owner, app and read-only. The app's
  containers get only the **app** credential as `DATABASE_URL`; the **migration job** gets the
  owner's (spec 30.5 "a dedicated release job, not every API container at startup").
- The users are created with `python manage.py setup_database_roles`, with the passwords in
  `HIMS_APP_DATABASE_PASSWORD` and `HIMS_READONLY_DATABASE_PASSWORD` (from the secret manager;
  `--write-env` is refused outside a developer PC).
- The deployment runs `python manage.py check_database_roles` and stops if it fails, so the app
  never starts with more rights than it needs (deploy pipeline, HIMS-OPS-005).
- Database activity logging for owner and break-glass sessions, with an alarm when break-glass
  signs in, comes with AWS (HIMS-OPS-019).

## Break-glass: emergency access

Only for a real emergency (for example, data must be corrected and the app cannot do it), and
only after approval by the people your incident procedure names.

1. Record the reason and the approver in a **security incident** (Compliance → Incidents).
2. The database administrator switches the user on for a short time, with a new password:
   `ALTER ROLE hims_<hospital>_breakglass LOGIN PASSWORD '<new>' VALID UNTIL '<in 2 hours>';`
3. Work only as that user. It has the app's rights, so it still cannot change the audit log.
4. Switch it off again: `ALTER ROLE hims_<hospital>_breakglass NOLOGIN;` The Database access tab
   shows a failed check until it is off.
5. Close the incident with what was done.

## Who can see the checks

**Compliance → Database access**, for everyone with `compliance.view` (administrator, auditor,
compliance officer). It is read-only on purpose: the app must never be able to raise its own
rights, so users and rights are changed only by the owner's command. Setting up or re-applying the
rights is written to the audit log ("Separate database users set up or their rights re-applied").

## How it is tested

`backend/common/tests/test_database_roles.py` creates the users inside each test and acts as them
(`SET ROLE`), so PostgreSQL checks every statement against that user's real rights:

- as the app: adding audit records works; changing, deleting or emptying the audit log, its chain
  or restore-drill evidence is refused; so are disabling or dropping triggers, dropping tables,
  creating tables and emptying any table;
- as the app: signing in, changing a facility, sealing the audit chain and the tamper check all
  still work (nothing in normal work needs more);
- as read-only: reading works, but password hashes, two-factor secrets and sessions are refused,
  and nothing can be written;
- break-glass is switched off and has only the app's rights;
- a new evidence table created later is protected as soon as `migrate` re-applies the rights;
- the setup command updates the env file without printing a password and keeps its line endings;
- only `migrate`, the setup command, `flush` and `createcachetable` use the owner; the test suite
  always does.
