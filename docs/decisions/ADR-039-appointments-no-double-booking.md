# ADR-039: Appointments: the database stops double booking; patients to move are worked out

**Status:** Proposed (2026-11-15) · **Items:** HIMS-OPD-002 · **Spec:** 4.6, 10, 28.4 · Builds on [ADR-038](ADR-038-opd-sessions-and-free-slots.md)

## Context

Spec 4.6 asks for "booking, rescheduling, cancellation". P0 part 01 §4 and §10 say: booking a slot
that is already taken is refused **even if two people try at the same moment** (one succeeds, the
other sees "This slot was just taken"); rescheduling keeps a link to the old appointment;
cancellation needs a reason; a doctor going on leave lists the affected appointments to reschedule
or cancel. D11 allows "up to N extra" bookings per session. Free slots are worked out from the
weekly sessions and exceptions, not stored (ADR-038), so there is no slot row to lock.

## Decision

1. **One table, `appointments`,** holding the patient, the doctor, the department (and facility),
   the session it was booked into (a weekly session or an extra session, exactly one), its start and
   end instants and its day on the facility's clock, new / follow-up, how it was booked (front desk,
   phone), a short reason (no history), the status (P0 part 03), whether it is over the slots, and
   who booked, moved or cancelled it, when and why.
2. **No double booking, by the database:** an exclusion constraint on (doctor `=`, time range `&&`)
   for appointments that are booked, checked in or with the doctor and **not** over the slots
   (`appointment_no_double_booking`, P0 part 02). Two bookings at the same moment: the second
   insert fails and the service answers 409 `SLOT_TAKEN` ("This slot was just taken").
3. **The service checks first, under a lock on the doctor's staff row:** the time is the start of an
   open slot of one of the doctor's sessions that day (ADR-038: not off for leave, a holiday,
   approved leave, posting, department or employment), not past, at most 180 days ahead; the
   patient's record is in use (not merged) and the patient is not booked elsewhere at that time.
   The lock is also what makes counting **bookings over the slots** right: they go only into a slot
   that is already booked, while the session's allowance (D11) lasts.
4. **Moving** cancels the old appointment as "moved to another time" and books the new one in the
   same transaction, linked both ways (`rescheduled_from`, one replacement each); a failed new
   booking leaves the old one as it was. **Cancelling** needs a reason (the patient asked, the
   hospital, the doctor not available) and is refused once the day is over. Nothing is deleted.
5. **Patients to move are worked out, not flagged.** A booked appointment still to come whose
   slot is now off (a doctor away, a holiday, approved leave, the session ended or its posting
   ended) is on the department's **To move** list, with why. Recording an exception answers with
   the booked patients it hits; the Leave page shows how many patients are booked during leave
   before it is approved. Nothing is cancelled or moved by itself.
6. **A session cannot change its slot length while patients are booked into its coming days**
   (their slots would no longer line up); move them, or end the session and add a new one.
7. **Restricted records (D23)** are booked, moved and cancelled only by people who may open them;
   anywhere appointments are listed, others see "Restricted record" and the MRN.

## Consequences

- Correct under concurrency without a slot table: the exclusion constraint is the single guarantee,
  tested with two bookings at the same moment, and broken directly in the invariants test.
- The To move list can never be stale and needs no job; it costs one small query per department
  (`appointment_booked_dept_idx`, booked appointments only) and the sessions of the doctors
  involved (measured in the volume check).
- A patient booked with two doctors at the same moment by two people at once is checked by the
  service (each booking locks a different doctor), not by a database rule: rare, harmless (the
  front desk sees both) and found by the queue (HIMS-OPD-003). Revisit if it happens.
- The facility day list for the OPD queue (P0 index `(facility, local_date, status)`) is added with
  HIMS-OPD-003, which uses it; adding it now made PostgreSQL pick it for a doctor's week.

## Revisit when

- Online booking from the patient portal (Phase 6) needs a slot held for a few minutes while the
  patient confirms.
- Waitlists are approved (P0 part 01 §4: "waitlist [PO to confirm]").
