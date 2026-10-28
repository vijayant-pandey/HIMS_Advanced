# ADR-013: Append-only audit log enforced in PostgreSQL

**Status:** Proposed — needs Security + Compliance approval. **Owner:** Security.

## Decision
- Audit events live in `audit_events`, separate from application logs (spec 13.4). Actor,
  resource and facility are stored as plain identifiers, not foreign keys, so audit history
  survives independently of the records it describes.
- A PostgreSQL trigger rejects `UPDATE` and `DELETE`. The ORM also refuses saves to existing
  rows and deletes.
- `TRUNCATE` is controlled through privileges: the runtime database role must not hold TRUNCATE
  or ownership of `audit_events`. Only the migration role owns it (HIMS-OPS-007).
- Change sets store before/after values for changed fields only. Fields named as sensitive
  (password, token, secret…) are redacted.
- Audit rows are written in the same transaction as the change. Authorization denials are written
  by the API exception handler after the failed transaction has rolled back, so they are kept.
- Searching the audit log is itself audited. Organization administrators do not hold
  `audit.view` (separation of duties).

## Deferred (with triggers)
- **Monthly partitioning:** when `audit_events` passes ~50M rows or retention deletes are needed.
- **Tamper evidence** (hash chain or periodic export to S3 Object Lock): before production
  (HIMS-SEC-010).
- **Read auditing of patient charts:** introduced with the patient domain. Expect high volume and
  size storage accordingly.

## Update 2026-10-28 (HIMS-AUD-003): reading the log
- **Audit log screen** for `audit.view` holders: filters for reference number (case-insensitive),
  person (name or email), area, event, outcome and date range. Names of people and facilities
  are looked up in the same query (audit rows keep no foreign keys, so the log survives any
  other data change). Event names come from `apps/audit/catalog.py`; a test fails if a new
  event has no label.
- **CSV export** (`GET /audit-events/export/`): newest first, at most 5,000 rows per file
  (`X-Export-Truncated` says if more matched). Cells that start with `= + - @` are prefixed so
  spreadsheets don't run them as formulas. Every search and every export is itself recorded
  (`audit.events.searched`, `audit.events.exported`, with the filters used).
- Bad filter values (e.g. a mistyped date) return a clear 400 instead of a server error.
- Still administrators cannot read the log (separation of duties).
