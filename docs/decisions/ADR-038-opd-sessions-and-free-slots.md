# ADR-038: OPD sessions and their free slots are worked out, not stored

**Status:** Proposed (2026-11-15) · **Items:** HIMS-OPD-001 (HIMS-OPD-002 builds on it) · **Spec:** 4.6, 10, 28.4

## Context

Spec 4.6 asks for "doctor availability, appointment calendars"; P0 part 01 §4 describes weekday
sessions with a slot length, extra bookings (D11) and validity, plus exceptions for leave, holidays
and extra sessions, and D10 says "slots per doctor session (e.g. 10 minutes)". Leave is already
asked for and approved on the Leave page (rotas, HIMS-STAFF-012), so the same leave must not be
entered twice. Appointments (HIMS-OPD-002) will be refused when a slot is taken, by a database rule.

Two ways to hold availability:

1. **Store every slot** as a row (generated weeks ahead by a job), and mark slots off when leave
   or a holiday is recorded.
2. **Store only the pattern** (weekly sessions and exceptions) and work out a day's sessions and
   slots when asked.

## Decision

1. **Store the pattern, work out the slots.** `doctor_schedules` holds the weekly sessions (doctor,
   department, weekday, clock times on the facility's clock, slot length, extra bookings, valid
   from / until); `schedule_exceptions` holds the doctors away, the holidays (a department or the
   whole facility) and the extra sessions. `apps/scheduling/availability.py` works out any day's
   sessions from them with a fixed number of queries.
2. **What takes a session off, in one place:** an OPD leave exception (all day or between two
   times), a holiday, **leave approved on the Leave page** (read from `leave_requests`, never
   copied), the doctor not working (suspended, long leave), not posted in the department that day,
   or the department closed. Leave asked for but not decided shows as "Leave asked" and leaves the
   session open.
3. **Slots are counted from the session's start.** A part taken off removes the slots it touches;
   the others keep their usual times (an hour away 11:00–12:00 leaves 09:00…10:50 and 12:00…).
4. **Days and hours of a session never change.** A change is a new session (the old one ends), so
   every past week can be shown as it was and future bookings are never moved silently.
5. **No overlap for one doctor**, in any department: checked by the service under a lock on the
   doctor's staff row, and for weekly sessions also by a PostgreSQL exclusion constraint (doctor,
   weekday, overlapping validity, overlapping clock times; `DATE + TIME` makes the times
   comparable as an immutable range).
6. **Appointments (HIMS-OPD-002) will store their own start and end instants** and be checked
   against the worked-out slots when booked; the "slot taken" rule is the appointments table's own
   exclusion constraint (P0 part 02). A session ending or a doctor going away then lists the
   booked patients to move (P0 part 01 §10), which this ticket prepares by returning the affected
   sessions.

## Consequences

- Nothing to generate, no job, no slot rows to keep in step: recording a leave or a holiday is one
  row, and cancelling it brings the sessions back at once.
- The rota and the OPD schedule cannot disagree about who is on leave.
- Reading a week costs a few small queries (sessions, exceptions, approved leave, postings); the
  volume check measures it (HIMS-DATA-004 part for slice 2B).
- Time-zone changes (daylight saving in US facilities) are handled when the day is worked out: a
  session is 09:00–13:00 on the facility's clock every week.
- A slot length change applies to the weeks it is worked out for; once appointments exist, a change
  that would leave a booking off its slot must be refused (noted for HIMS-OPD-002).

## Revisit when

- Booking needs slots locked or reserved for a while (e.g. online booking from the portal, Phase 6):
  a short-lived hold table may be added beside the worked-out slots.
- Reading the week becomes slow at a hospital's size (the volume check fails).
