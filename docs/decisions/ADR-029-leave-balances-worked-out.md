# ADR-029: Leave balances are worked out, never stored

**Status:** Proposed (2026-11-09) · **Item:** HIMS-STAFF-013 · **Spec:** 4.3, 10, 28

## Context

A leave balance could be kept as a number that goes up and down, or worked out from the facts each
time. A stored number has to be updated by every path that touches leave: approving, cancelling,
termination, the admin console, restoring a backup. Any path that misses it leaves a wrong number,
and nothing shows which is right. Spec 28 asks for one source of truth per fact.

## Decision

**1. Worked out each time.** `Left = entitled + carried in + adjustments - approved days`. The facts
are the entitlements, the adjustments and the approved leave.

**2. Entitlements apply from a year and do not rewrite the past.** A row applies from its year until a
later one replaces it. New rows start this leave year or later, and rows from earlier years cannot
change. Without this, changing "20 days" to "25" would silently change every past balance, and every
carry-over since.

**3. Corrections are append-only.** Opening balances and corrections are adjustments with a reason,
which the database refuses to change or delete, the same trigger as the audit log.

**4. Going over asks, and never silently passes or blocks.** Hospitals differ, so approving over the
balance is allowed with an explicit tick and a reason, which goes in the audit log. Approval locks the
person's staff record, so two approvers at the same moment cannot both spend the same days (spec 10).

**5. Untracked by default.** No entitlement, no balance, no limit. Installing this changes nothing
until a hospital sets a number.

## Consequences

- Each read walks from the first tracked year for that person. A whole department costs a few queries,
  because leave and adjustments are fetched once for everyone (a test pins this).
- The walk grows by one step a year. If it ever becomes slow, closed years can be stored as a cache of
  the same calculation, without changing the rules.
- Every calendar day counts, as `LeaveRequest.days` always has. Working patterns and public holidays
  are not modelled yet.
- Cancelling leave that has started returns all its days, because leave has no actual end date.
