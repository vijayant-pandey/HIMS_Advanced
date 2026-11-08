# Backups and restore drills

**Ticket:** HIMS-OPS-009 · **Spec:** 13.3 ("backups, restoration testing"), 13.5 (security test:
"a database restore recovers records but fails to restore required audit relationships"), 17.3
("a backup is not a recovery strategy until it has been restored successfully and critical
relationships, files, clinical records and audit history have been verified"), 23 (readiness:
"restore drills completed"), 27.1 ("maintain evidence that restores have been tested"). Decision:
[ADR-025](../decisions/ADR-025-backups-and-restore-drills.md).

## In one paragraph

A **backup** copies the database and every stored document from one moment. A **restore drill**
puts that backup back into a **separate copy** (a new database and a new folder; the live system
is never touched), checks that everything came back, then removes the copy. Each drill's result is
kept as evidence that nobody can change, and both steps go into the audit log. A backup only
counts once a drill has passed on it.

## Where this runs

| Where | Backups | Restore drills |
|---|---|---|
| **Developer PC** (local) | HIMS makes them: Backups page or `python manage.py backup_database` | HIMS runs them: Backups page or `python manage.py restore_drill` |
| **Hosted** (Development, QA, Staging, Production) | The cloud database service (automatic backups, point-in-time recovery) and versioned document storage | Cloud runbook: restore a snapshot into a separate database, then run the same checks (HIMS-OPS-004, waits for AWS) |

In a hosted environment the buttons are switched off and the page says so: copying a live hospital's
database onto an application server would itself be a data-protection risk.

## What a restore drill checks

| Check | What it proves |
|---|---|
| The backup file is complete and unchanged | The database file's fingerprint (SHA-256) still matches the one taken when it was made. A changed file is refused before anything is restored |
| PostgreSQL restored the backup without errors | `pg_restore` stopped at no error |
| Same database version (migrations) | The copy has exactly the same migrations |
| Every table came back with the same rows | Each table has the same number of rows **and** the same fingerprint of all its rows, so one changed or missing row is caught (no record content is stored for this) |
| Every database rule came back | Keys, links between tables, uniqueness, overlap rules (rotas and leave), all switched on |
| Every database trigger came back and is switched on | Including the triggers that keep the audit log append-only |
| Every index, extension and counter came back | Speed, the overlap extension (`btree_gist`) and number counters |
| **Audit log chain verified with this hospital's keys** | The tamper check (HIMS-SEC-010) runs on the copy: every link recomputed, and the end of the chain matches the backup |
| **Audit records still linked** | Every chain link points to its audit record, audit records still name people who exist, and the audit tables are still append-only. This is the spec 13.5 test case |
| Encrypted values can be read | Values encrypted with the keys kept outside the database (two-factor secrets, unsent messages) can be read, so the keys and the backup belong together |
| Every stored document came back unchanged | Every document the database lists is in the restored folder with the same fingerprint and size |

The drill also records **how long the restore took** and **how old the backup was**. These are the
first real numbers for the recovery time (RTO) and the data that could be lost (RPO). The targets
themselves are a decision for you with operations and clinical leads (spec section 36, "RTO/RPO").

## On your PC, step by step (Windows, CMD)

You need PostgreSQL's command line tools (`pg_dump`, `pg_restore`). They come with PostgreSQL; HIMS
finds them on its own in `C:\Program Files\PostgreSQL\<version>\bin`. If they are somewhere else, add
`HIMS_PG_BIN_DIR=<that folder>` to `backend\.env`. The tools must be the same version as the database
or newer. If you use the database from `docker-compose.yml`, set
`HIMS_PG_DOCKER_CONTAINER=<container name>` instead.

**In the app:** sign in as the administrator → **Backups** → **Make a backup now** (it asks
"Confirm it's you" if you have not confirmed recently) → **Run restore drill** on that backup →
open the drill to see every check.

**From the command line:**

```
cd C:\Users\vpand\OneDrive\Desktop\HIMS\backend
.venv\Scripts\activate.bat
python manage.py backup_database
python manage.py restore_drill
```

`restore_drill` restores the newest backup (or `--backup <name>`) and prints every check. It ends
with `PASSED` or `FAILED`, and exits with an error when a check fails.

For the **US hospital**, run the same with `set HIMS_ENV_FILE=.env.us` first, then
`set HIMS_ENV_FILE=` afterwards. Each hospital has its own backup folder.

## Where backups are kept, and keeping them safe

- Folder: `backend\backups\<hospital>\<backup name>\` (or `HIMS_BACKUP_DIR`). Each backup holds
  `database.dump`, `documents\` and `manifest.json` (counts and fingerprints only, no record
  contents).
- A backup holds **every record**, including password fingerprints and personal details. Keep the
  folder private. It is excluded from git (`.gitignore`) and must never be copied to shared drives
  or chat.
- The **keys are not in the backup**: `HIMS_FIELD_ENCRYPTION_KEYS` and `HIMS_AUDIT_CHAIN_KEYS` live
  in `.env` (and in the secret manager when hosted). Without them, encrypted values cannot be read
  and the audit chain cannot be verified. Keep the keys safe **separately** from the backups.
- Old backup folders can be deleted by hand when no longer needed. The record that they existed,
  and their drills, stay on the Backups page.

## Who can do what

| Permission | Who has it | Allows |
|---|---|---|
| `recovery.view` | Organization administrator, auditor | See backups and drill results |
| `recovery.manage` | Organization administrator | Make backups (a sensitive action: "Confirm it's you"), run drills. Two-factor sign-in is required |

The **admin console** has the same pages (read-only evidence) with **Make a backup now** and, on a
backup, **Run a restore drill on this backup**.

## When a drill fails

1. Do **not** rely on that backup.
2. Open the drill: the failed check names what is wrong (a table, a rule, a document, the audit
   chain).
3. Make a new backup and run a drill on it. If it fails again the same way, the live system itself
   may have a problem: for audit checks, run the **Audit integrity** check and follow the incident
   procedure.

A failed drill also writes an error line (`restore_drill_failed`) for monitoring to alert on
(HIMS-OPS-004, with AWS).

## How it works (for developers)

- `apps/recovery/services.py`: `create_backup` takes the inventory and runs `pg_dump --snapshot`
  inside **one** database snapshot, so the inventory describes exactly what the dump holds.
  `restored_copy` creates the separate database (`<name>_drill_<time>`), runs `pg_restore
  --exit-on-error`, copies the documents into a temporary folder, and always removes both.
  `verify` runs the checks.
- `apps/recovery/inventory.py`: row counts and fingerprints per table, migrations, rules, triggers,
  indexes, extensions, counters, audit chain and document fingerprints. Rules are compared by
  meaning: PostgreSQL prints casts differently after a restore.
- `apps/recovery/pg_tools.py`: finds and runs the tools; the password goes in the environment, never
  on the command line; error text passes the log filter (HIMS-SEC-019).
- Tests: `apps/recovery/tests/test_restore_drill.py` runs real backups and drills, including a
  restore that loses the audit links (TRUNCATE of the chain, a dropped append-only trigger), a
  missing document, a changed backup file and a file PostgreSQL cannot read. In CI the tools run
  inside the database container (`HIMS_PG_DOCKER_CONTAINER`); a CI test makes sure of it.

## Known gaps (recorded)

- **Hosted environments:** snapshot-based restore drills and alarms come with AWS (HIMS-OPS-004,
  HIMS-OPS-015 for versioned document storage).
- **Emptying the audit tables in one go (`TRUNCATE`)** is not blocked by the append-only triggers;
  the separate database users of HIMS-OPS-007 take that right away from the application.
  **Closed 2026-11-08:** see [separate database users](database-users.md).
- **RTO/RPO targets** are a decision (spec 36); the drills measure what is achieved today.
