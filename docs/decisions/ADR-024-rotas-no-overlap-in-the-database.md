# ADR-024: Rotas and leave: shifts stored as instants, overlaps refused by the database

**Status:** Proposed. **Owner:** Engineering lead. **Ticket:** HIMS-STAFF-012.
**Spec:** 4.3 (shift schedules, leave, on-call), 10 (concurrency and data integrity), 13.2.
Design: [rotas-and-leave.md](../architecture/data-architecture/rotas-and-leave.md).

## Decision

- **A shift stores its real start and end** (`starts_at`, `ends_at`, timestamps with time zone),
  worked out once from the day, the shift type and the facility's time zone. Editing a shift
  type later does not move shifts already planned, a night shift that crosses midnight or a
  daylight-saving change has its true length, and "who is on call now" is a simple range query.
- **The database refuses double booking.** PostgreSQL exclusion constraints refuse two scheduled
  shifts for one person that overlap in time, and two asked-for or approved leave periods for one
  person that overlap. They need the standard `btree_gist` extension (shipped with PostgreSQL,
  available on Amazon RDS), switched on by the first rota migration.
- **The app checks first, the database is the backstop.** The app gives a clear message (which
  shift is in the way); the constraint catches the race when two planners book the same person
  at the same moment (spec 10: "the database must enforce the invariant").
- **Leave is a request with a decision**, never self-approved; approving over planned shifts
  needs an explicit "cancel those shifts".
- **Privacy:** the rota shows that someone is away, not why; the kind of leave is shown only to
  people who decide leave.

## Rejected

- **Store only the day and the shift type.** Every overlap and "on call now" check would have to
  rebuild times in every time zone, and a shift type edit would silently rewrite history.
- **App-only overlap checks with row locks.** Two planners working on different departments lock
  different rows, so a person could still be double-booked across departments.

## Consequences

- Hosted databases must allow `btree_gist` (it does on RDS and on the local PostgreSQL 17/18).
- Phase 2 appointments can use the same pattern (spec 4.6 "without double booking").
- Leave balances, shift swaps and minimum staffing are later tickets (HIMS-STAFF-013 to 015).
