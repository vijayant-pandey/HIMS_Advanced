# Leave balances and entitlements (HIMS-STAFF-013)

**Spec:** 4.3 "leave". **Approval:** the product owner said "fine for now" on 2026-11-08, on the basis
that the hospital sets the entitlements itself ([decisions log](../status/decisions-log.md), item 6).
Decision record: [ADR-029](../decisions/ADR-029-leave-balances-worked-out.md).

**Nothing changes until a hospital sets an entitlement.** A kind of leave with no entitlement has no
balance and no limit, and works exactly as it did before.

## Setting it up

1. **Hospital settings → Edit → Leave year starts in:** January by default; April for an April to
   March leave year. A leave year is named after the calendar year it starts in.
2. Menu → **Leave → Entitlements → Add an entitlement** (needs `leave.policy.manage`, held by the
   organization administrator and the HR / credentialing officer):
   - **Days per leave year**, for one kind of leave.
   - **Most days carried into the next year.** 0 means unused days are lost.
   - **Someone joining during the year gets a share by whole months.** On by default; untick it to
     give the full number. The month they join in counts, and half a day rounds up.
   - **Keep a balance:** untick it in a later year to stop tracking from that year.
3. Opening balances: **Leave → Balances → Adjust**, e.g. +5 "Balance brought from the old system".

## How a balance is worked out

```
Left = entitled + carried in + adjustments - approved days
```

- It is **worked out each time, never stored**, so it cannot drift away from what really happened.
- **Waiting** requests are shown separately and are not taken off until approved.
- **Carried in** is what was left last year, up to the limit. An overdrawn year carries nothing, debt
  or credit.
- Leave across two leave years counts each day in its own year.
- An entitlement applies from its year until a later one replaces it.
- **Past years stay as they were:** a row can only start this leave year or later, and a row from an
  earlier year cannot be changed. Add a new one instead.

## Going over the balance

Anyone can still **ask** for leave. When an approver opens a request that would go over, HIMS says by
how many days. Approving needs a tick on **Approve anyway** and a reason, which goes in the audit log
with the number of days over.

## Who sees what

| Who | Sees |
|---|---|
| Everyone with a staff record | Their own balance on **My schedule** |
| People who decide leave for a department (`leave.approve`) | **Balances** for that department, and **Entitlements** |
| `leave.policy.manage` | Also sets entitlements and adjusts balances |

Nobody adjusts their own balance. An adjustment needs a reason and is **append-only**: a wrong one is
corrected by adding another, and the database refuses any edit or delete.

## Limits to know

- **Every calendar day counts**, including weekends and holidays, as leave always has here. A hospital
  that does not count weekends cannot express that yet.
- **Whole days only.**
- **Cancelling leave that has already started gives back all its days**, because leave has no "actual
  end date" yet. Correct it with an adjustment.
- **One entitlement for everyone**, not per job title or department.

## Admin console

- **Leave entitlements:** same rules; rows from earlier years are read-only.
- **Leave balance adjustments:** add one under the same rules; existing ones are read-only.
- **Leave requests:** a separate action, "Approve selected leave even if it goes over the balance".
- On a **Staff member's** page, a read-only **Leave balance this year** section.
- On the **Organization** page, **Leave year start month**.

## Tables

`leave_entitlements` and `leave_balance_adjustments` (append-only), and
`organizations.leave_year_start_month`: see the
[data dictionary](../architecture/data-architecture/data-dictionary.md).
