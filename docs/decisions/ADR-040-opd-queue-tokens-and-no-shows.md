# ADR-040: The OPD queue: tokens per doctor and day, walk-ins without a slot, a no-show job

**Status:** Proposed (2026-11-15) · **Items:** HIMS-OPD-003 · **Spec:** 4.6, 28.4 · Builds on [ADR-039](ADR-039-appointments-no-double-booking.md)

## Context

P0 part 01 §4 (D10) gives each doctor's day **token numbers**: a walk-in gets the next token, a
booked patient gets theirs at check-in, and the OPD queue shows each doctor's tokens: waiting, with
the doctor, done. D12: a patient not checked in by the end of the session is a **no-show**, marked
automatically and undone by the front desk the same day. Part 02 puts `token_number` on
`appointments` with `UNIQUE(staff, local_date, token_number)` and lists a facility day index
(facility, local date, status). Part 03 creates the visit (encounter, with its visit number) at
check-in; encounters come with HIMS-CLIN-001 (slice 2C).

## Decision

1. **Check-in and walk-ins are on `appointments`.** Check-in turns a booked appointment (on its day;
   also one marked "did not come" that day: the patient came late) into **checked in** with the
   doctor's next token, when and by whom. A **walk-in** is an appointment whose source is
   `walk_in`, created checked in, with a token, in the doctor's session today (the one running, else
   the next, else the last: the doctor may still be seeing patients).
2. **A walk-in takes no slot.** The no-double-booking rule (exclusion constraint) is rebuilt to
   leave walk-ins out, and the free-slot calculation ignores them, so booked patients keep their
   slots. Its start is the minute it arrived, its end one slot later.
3. **Tokens per doctor and day,** in arrival order, given under the lock on the doctor's staff row
   (as bookings are); the database refuses a number twice (`appointment_one_token`, partial unique
   index) and a checked-in appointment without its token (`appointment_checked_in`).
4. **The queue moves with Call next and Seen, by the front desk, until visits exist.** Call next
   calls the lowest waiting token of the doctor in that department in to the doctor and marks
   whoever was with the doctor as seen; Seen ends the last one. A waiting patient may leave (kept as
   cancelled "Left before being seen", with the token). With HIMS-CLIN-001 the doctor's start and
   finish of the visit take this over (P0 part 03: `encounters.manage`), and check-in also creates
   the visit with its number in the same transaction.
5. **The no-show job runs every 15 minutes** (`scheduling.mark_no_shows`, in `config/schedule.py`,
   so it runs with Celery beat or `run_scheduled_jobs`): booked appointments whose slot has ended and
   whose session has ended become **did not come**, at most 500 a run, each under a row lock and only
   if still booked; safe to run again. The front desk may mark one once its time has passed, and
   undo it the same day **before the session ends** (after it the job would mark it again; a late
   patient is checked in instead).
6. **The queue is per department,** like the Appointments page: it reads the department's doctors'
   day through `appointment_staff_day_idx`. P0's facility day index is **not added**: nothing reads
   by facility and day, and it made PostgreSQL read a doctor's week through it (HIMS-OPD-002). The
   OPD daily list per facility (HIMS-RPT-002) adds it if its volume check needs it.
7. **The job's index is on the end, not the start** (`appointment_booked_end_idx`, booked only): a
   start index was chosen by the To move list (booked ones still to come) instead of its own.
8. **Restricted records:** check-in and walk-ins pick a patient, so they need the right to open a
   restricted record; moving the queue (call next, seen, left, did not come) shows nothing more and
   does not.
9. **Today is the hospital's today.** The queue screen asks the server without a date, so a browser
   in another time zone still sees and works on the right day.

## Consequences

- No new table: the day of the visit is a few columns and four database rules on `appointments`,
  each broken on purpose by the invariants test.
- Walk-ins never push booked patients out of their slots, and a doctor's free slots stay the
  bookable ones.
- Until HIMS-CLIN-001, "Seen" is a front desk mark, not a finished visit with a signed note; the
  OPD daily list and reports must use the visit once it exists.
- A token is never reused in a day, even when a patient leaves; numbers can have gaps only across
  departments of the same doctor (one series per doctor and day).

## Revisit when

- Visits exist (HIMS-CLIN-001): the doctor's start and finish replace Call next and Seen; check-in
  issues the visit number.
- A waiting-room display of called tokens is wanted (HIMS-OPD-008, PO to decide).
- The OPD daily list per facility is built (HIMS-RPT-002): measure the facility day index then.
