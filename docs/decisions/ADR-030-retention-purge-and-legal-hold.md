# ADR-030: Retention purge limited to housekeeping records, with waiting periods and legal holds

**Status:** Proposed (2026-11-10) · **Item:** HIMS-COMP-006 · **Spec:** 4.25, 13.3, 28.1 #5, 28.2

## Context

Spec 4.25 asks for "retention, legal holds, export controls and deletion restrictions", and spec 28.1
asks for lifecycle and retention rules for every table. Keeping personal data longer than needed is
itself a risk (DPDP section 8(7)), yet deleting the wrong record cannot be undone. LEGAL approved on
2026-11-08 that the hospital sets the periods and that nothing is deleted until it does (decisions
log #7). Spec 28.2 forbids erasing signed clinical or financial facts with a generic delete. The
audit log is protected by an append-only trigger and a hash chain, so deleting from it would break
the chain.

## Decision

**1. Only housekeeping records can be purged.** A fixed list in code (`apps/compliance/retention.py`):
ended sign-ins, sent or finished messages, closed invitations and password resets, browser block
reports, and reviewed console refusals. The audit log, staff records, compliance registers and, from
Phase 2, clinical and financial records are not on the list and cannot be added from a screen. The
audit log needs an archive with an "archived up to link N" marker first (HIMS-COMP-007, hosting
stage).

**2. Kept for ever by default.** Each kind has a rule with an empty period. Installing the purge
deletes nothing.

**3. Minimums.** Each kind has a minimum period in code (365 days for sign-ins and console refusals,
the CERT-In and DPDP log periods; 90 for messages; 30 for the rest), so a typing mistake cannot empty
a table. Counsel sets the real periods; the minimum is only a floor.

**4. Shorter periods wait 7 days.** Setting the first period, or a shorter one, is recorded as waiting
and only applies at the first purge after 7 days. It can be cancelled until then. A longer period, or
"keep for ever", applies at once because it deletes nothing.

**5. Legal holds always win.** A hold covers chosen kinds (none = every kind) and, optionally, only
the records about one person. Holds are never deleted. Releasing one needs a reason. Placing and
releasing holds, setting periods and running the purge need `compliance.manage` and a recent
"confirm it's you".

**6. Evidence without contents.** Each run is a row in `retention_purge_runs`, append-only through the
same trigger as the audit log. Each run also writes an audit event. Both hold counts per kind, never
the deleted rows' contents.

**7. Safe to run at any time.** The purge runs daily through Celery beat, from the app, the console or
`purge_expired_records`. A PostgreSQL advisory lock allows one run at a time. It deletes in batches
of 2,000 in short transactions and stops at 50,000 rows per kind per run. The rest go the next day.

## Consequences

- Nothing changes for a hospital until someone sets a period. The Compliance → Retention tab shows
  what a purge would delete now, before anything goes.
- A hold on one person matches messages by their account's email (and who asked for the message).
  Messages sent to an address no longer linked to an account cannot be matched; a hold on the whole
  kind covers them.
- Deleting old sign-ins removes the device and address history from "My sign-ins" and the console. The
  audit log keeps every sign-in event, so investigations still have them.
- Adding a new purgeable kind is a code change with tests, reviewed like any other.
