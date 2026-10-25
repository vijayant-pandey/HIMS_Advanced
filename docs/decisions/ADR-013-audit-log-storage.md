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
