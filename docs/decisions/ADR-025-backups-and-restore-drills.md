# ADR-025: Backups and restore drills checked against an inventory taken in the same snapshot

**Status:** Proposed · **Date:** 2026-11-08 · **Ticket:** HIMS-OPS-009 · **Spec:** 13.5, 17.3, 23,
27.1

## Context

The spec asks for restore drills with "verified reconciliation afterward" and names a security
test: "a database restore recovers records but fails to restore required audit relationships".
A backup job that reports "success" proves nothing about whether the copy can be restored. Cloud
backups (RDS snapshots, point-in-time recovery) wait for the AWS decision, but the checks a drill
must run can be built and proven now.

## Decision

1. **Backup = PostgreSQL custom-format dump + document folder + inventory.** The inventory (row
   count and fingerprint of all rows per table, migrations, constraints, triggers, indexes,
   extensions, sequences, audit chain head, document fingerprints) is taken inside one
   `REPEATABLE READ` transaction whose snapshot is exported to `pg_dump --snapshot`. Inventory and
   dump therefore describe exactly the same moment, even while people keep working.
2. **A drill restores into a new database and folder, never over the live ones**, then compares the
   copy with the inventory and runs the audit tamper check on it with this deployment's keys. The
   copy is always removed afterwards.
3. **Evidence is append-only** (database trigger, like the audit log), and every backup and drill is
   an audit event.
4. **Only on a developer PC from the app.** Hosted environments use the cloud database service; their
   drills restore a snapshot into a separate database and run the same checks (runbook with AWS).
5. **Rules are compared by meaning**: casts, brackets and spaces are ignored, because PostgreSQL
   prints a re-read rule differently after a restore.
6. **The tools are PostgreSQL's own** (`pg_dump`, `pg_restore`), found on the PC or run inside the
   database container (docker-compose and CI). The password is passed in the environment.

## Consequences

- The spec 13.5 restore test is an automated test in CI with real `pg_dump`/`pg_restore`.
- Keys are not in the backup; recovering a hospital needs the backup **and** its keys.
- Fingerprinting every row is linear in the data size: fine for drills; for very large hosted
  databases the drill may compare a sample per table (revisit with HIMS-DATA-002 volumes).
- `TRUNCATE` of audit tables is not blocked by row triggers; HIMS-OPS-007 removes that right from the
  application's database user.

## Alternatives considered

- **Only counting rows:** misses changed rows and lost links. Rejected.
- **Comparing the restored copy with the live database:** the live data moves on while the drill
  runs. Rejected in favour of the snapshot inventory.
- **`pg_dumpall` / file-system copies:** include other databases and roles; not portable between
  Windows and Linux. Rejected for local drills.
