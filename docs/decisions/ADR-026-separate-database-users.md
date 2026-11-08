# ADR-026: Separate database users, with rights derived from the database and the data dictionary

**Status:** Proposed · **Date:** 2026-11-08 · **Ticket:** HIMS-OPS-007 · **Spec:** 13.2, 13.4, 17.2,
30.5 · **Builds on:** [ADR-013](ADR-013-audit-log-storage.md) (append-only audit log)

## Context

Until now the app connected as the database owner. The append-only triggers stopped `UPDATE` and
`DELETE` on the audit log, but the owner could still `TRUNCATE` it, disable or drop the triggers,
or drop the tables. Anyone who took over the app (or its credentials) had those powers. The spec
asks for separate credentials per role: runtime, migration, read-only reporting, support/break-glass
(30.5).

## Decision

1. **Four users per hospital deployment**, named `hims_<deployment>_{app,readonly,breakglass}`
   plus the existing owner. Per deployment because two hospitals may share a database server
   (both local databases do).
2. **The app user gets row rights only:** `SELECT, INSERT, UPDATE, DELETE` on ordinary tables,
   `SELECT, INSERT` on evidence tables, sequence use; never `TRUNCATE`, ownership, `CREATE` on the
   schema, superuser, `CREATEDB` or `CREATEROLE`.
3. **Evidence tables are found, not listed:** every table with a trigger calling an append-only
   function (`audit_events_reject_mutation`, `audit_reject_mutation`). A new evidence table is
   protected as soon as it has the trigger.
4. **Credential columns come from the data dictionary** (level Secret), so the read-only user
   gets column-level `SELECT` without them; `django_session` is hidden entirely.
5. **Rights are re-applied after every `migrate`** (post-migrate signal, run as the owner), and
   default privileges let the app use a new table at once.
6. **Only schema commands use the owner** (`migrate`, `setup_database_roles`, `flush`,
   `createcachetable`) through `HIMS_MIGRATION_DATABASE_URL`; backups and drills (which create a
   database) and the test suite use it too. Everything else uses `DATABASE_URL`, the app user. In
   hosted environments the migration job simply gets the owner's credential as its
   `DATABASE_URL`.
7. **Passwords are sent as SCRAM verifiers**, so a plain password never reaches a database log.
   On a developer PC `--write-env` generates them and updates the env file without printing them.
8. **Break-glass is a separate user that is switched off** (`NOLOGIN`) and is a member of the app
   user: when switched on for an emergency it has the app's rights, never the owner's.
9. **The checks are read from the database** (`has_table_privilege` and friends), shown on the
   Compliance page and in `check_database_roles`, which a deployment runs before starting the app.

## Consequences

- `TRUNCATE` of the audit log, disabling or dropping its triggers, and dropping tables are no
  longer possible for the running app (closes the gap noted in ADR-013 and ADR-025).
- A developer must run the setup once per hospital; until then the app works as before and the
  Compliance page says it is not set up.
- Migrations must run as the owner (they already do through `migrate`).
- Database activity logging for owner and break-glass sessions needs the managed database
  (pgaudit; HIMS-OPS-019, AWS).

## Alternatives considered

- **Hand-maintained table lists:** forgotten for the next evidence table. Rejected.
- **Row-level security:** solves a different problem (which rows), adds cost to every query.
  Not needed for this.
- **Revoking `TRUNCATE` from the owner:** the owner can grant it back to itself. Rejected.
