# The OPD queue: check-in, tokens, walk-ins and patients who did not come (HIMS-OPD-003)

Phase 2 → Spec §4.6 → Slice 2B. Rules: [Phase 2 P0 part 01 §4](../p0/phase-2-patients/01-functional-requirements.md)
("Walk-ins and tokens (D10): a walk-in is checked in directly and gets the next token number for
that doctor and day. Booked patients get their token at check-in. The OPD queue screen shows tokens
per doctor: waiting, with doctor, done. … Not checked in by the end of the session → no-show
(D12)"), [part 02](../p0/phase-2-patients/02-database-design.md) (`token_number`, one per doctor and
day), [part 03](../p0/phase-2-patients/03-state-machines.md) ("Appointment": check in, walk in,
mark no-show, undo no-show) and [part 06](../p0/phase-2-patients/06-screens-api-tests.md) ("OPD queue
(today): per doctor: token, patient, status, time waiting; buttons Check in, Walk in, Call next").
How it works inside: [data design, part 3](../architecture/data-architecture/scheduling.md#part-3-the-opd-queue-hims-opd-003),
[ADR-040](../decisions/ADR-040-opd-queue-tokens-and-no-shows.md). Booking comes first:
[appointments](appointments.md) (HIMS-OPD-002).

The visit itself (visit number, vitals, the doctor's notes) comes with slice 2C (HIMS-CLIN-001 and
on). Until then the front desk moves the queue (**Call next**, **Seen**); afterwards the doctor's
start and finish of the visit do.

## Who does what

| Person | Can | Permission |
|---|---|---|
| Front desk (Receptionist role) | Check patients in, check in walk-ins, call the next patient, mark seen, left, did not come (and undo it) | `appointments.manage` |
| OPD scheduler | The same, in their department or branch | `appointments.manage` |
| Head of department, branch and hospital administrators | See the queue (no buttons) | `appointments.view` |
| Medical records | Check in a **restricted** record's patient (others see "Restricted record") | `patients.restricted` with a booking role |

## The day of the visit

1. Open **OPD queue** in the menu. It shows **today on the hospital's clock** (even if your
   computer is in another time zone). Choose the **department**.
2. Each doctor with a session today has a box: the session hours, counts (**Waiting**, **With the
   doctor**, **Seen**, **Still to come**, **Did not come**) and the patients by token.
3. **A booked patient arrives:** press **Check in** on their row. They get the doctor's **next
   token** (1, 2, 3 … in the order patients arrive, not their booked time) and show as
   **Waiting N min**.
4. **A patient without an appointment:** press **Walk in** in the doctor's box, find the patient
   (MRN, phone, ID number or name; register them on the Patients page first if they are new), choose
   New or Follow-up, a short reason, and press **Check in**. A walk-in takes **no slot**: the booked
   patients keep theirs. The doctor needs an OPD session in the department today (it may have
   started or even ended: the doctor may still be seeing patients).
5. **The doctor is ready:** press **Call next**. The lowest waiting token goes **With the doctor**;
   whoever was with the doctor is marked **Seen**. For the last patient press **Seen** on their row.
6. **A waiting patient leaves:** press **Left** on their row (kept on record as "Left before being
   seen", with their token).

## Patients who did not come

- Every 15 minutes the hospital's job marks booked patients who were not checked in by the **end of
  their session** as **Did not come** (D12). They leave the **To move** list on the Appointments
  page.
- The front desk can mark one earlier (**Did not come**), once their booked time has passed.
- Marked by mistake? **Undo** books them again, the same day and before the session ends.
- The patient came late after all? **Check in** works on a "did not come" row the same day: they
  get the next token.

## What is refused, and why

| You see | Because |
|---|---|
| "Already checked in: token 3" | Pressed twice, or someone else checked them in |
| "Patients are checked in on the day of their appointment (…)" | The appointment is another day: move it, or check them in as a walk-in |
| "Dr … is not seeing patients at this time (Away): move the appointment" | The doctor was recorded away or on leave: the patient is on the To move list |
| "Dr … has no OPD session in … today" | Walk-ins only join a doctor's session today |
| "The patient is already waiting for Dr … (token 2)" | One patient waits in one queue at a time |
| "The patient has an appointment with Dr … at 10:20 today: check them in instead" | Use their booking, not a walk-in |
| "Nobody is waiting for Dr …" | Call next with an empty queue |
| "Its time has not come yet" | "Did not come" only after the booked time |
| "Its session is over: if the patient came, check them in instead" | Undo is for the same session only |
| "This is a restricted record" | Only medical records (or emergency access) may check in a restricted record |

## Other days

Choose another day (or **Previous day**) to see that day's queue as it was: no buttons, since
patients are checked in on the day only. The **Appointments** page shows each patient's token next
to their status.

## In the admin console

**Doctor schedules (OPD) → Appointments:**

- **OPD queue** (top right): choose the department; today's patients by doctor with tokens and
  status, a **Call next** button per doctor and a **Walk in** form (the patient's exact MRN, doctor,
  visit, reason).
- Actions on the list: **Check in selected**, **Mark selected: seen by the doctor**, **left before
  being seen**, **the patient did not come**, **Undo did not come**.
- Columns **Token** and **Source** (Walk-in, front desk, phone), filter by source.
- **Outbox → Scheduled jobs** (and the **Background jobs** page in the app) lists "Mark booked OPD
  patients who did not come" with how often it runs and its last run.

Every check-in, walk-in, call, seen, left, did not come and undo is in the audit log (area
**Appointments (OPD)**); the job's markings have no person (the system).

## Demo hospitals

Each branch has **today's queue** when the demo is built: four patients booked into a doctor's
session (an extra session "Demo OPD queue", 08:00–20:00, is added when no doctor works that day),
three checked in out of slot order (tokens 1–3) and a walk-in (token 4); token 1 seen, token 2 with
the doctor, tokens 3 and 4 waiting; the fourth booked patient still to come or did not come. Sign in
as `frontdesk.<branch>@` to move the queue, `hod.<branch>@` to look. Today moves on: on another day,
choose the day it was built, or add a new day's queue with `add_demo_opd_queue` (on the hosted
Development hospital: `--hosted-development`, [hosting](render-neon-hosting.md)).
