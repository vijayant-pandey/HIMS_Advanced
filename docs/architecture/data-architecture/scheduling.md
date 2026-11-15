# Doctor schedules: OPD sessions and exceptions (HIMS-OPD-001)

Phase 2 → Spec §4.6 → Slice 2B. Design: [P0 part 02](../../p0/phase-2-patients/02-database-design.md)
("doctor_schedules and schedule_exceptions"); decision: [ADR-038](../../decisions/ADR-038-opd-sessions-and-free-slots.md);
how-to: [doctor schedules](../../workflows/doctor-schedules.md). Tables, columns and constraints in
full: [data dictionary](data-dictionary.md#doctor-opd-schedules) (generated).

This page is also the **Artifact A review** (spec 28.8) of these two tables, done with the ticket as
HIMS-DATA-004 asks for each later P0 domain. Appointments (HIMS-OPD-002) add their own table and
review to this page.

## 1. Tables

| Table | One row is | Key rules (database) |
|---|---|---|
| `doctor_schedules` | One weekly OPD session: a doctor, a department (and its facility), a weekday, start and end on the facility's clock, slot minutes (5–120, default 10), extra bookings (0–20, D11), valid from, valid until (empty = no end), `is_active` (off = withdrawn before its first day), note | ends after it starts; weekday 0–6; slot and extra-booking ranges; until ≥ from; **no two active weekly sessions of one doctor overlap** on the same weekday and dates (`doctor_schedule_no_overlap`, exclusion constraint) |
| `schedule_exceptions` | A doctor away (`leave`), a holiday (`holiday`: a department, or the whole facility when the department is empty) or an extra session (`extra_session`), from a first to a last day, all day or between two times | last day ≥ first; both times or neither, end after start; times only on one day; a holiday has no doctor, leave and extra sessions have a doctor and a department; an extra session is one day with its hours, slot minutes and extra bookings |

Every row has `organization`, `created_at`, `updated_at` and `version`; foreign keys are `PROTECT`.

## 2. Ownership

The **outpatient (scheduling) domain** owns both tables; `apps/scheduling/services.py` writes them,
for the API and the admin console alike. It **reads** other domains and never writes them:

| Read from | Why |
|---|---|
| `staff_members` (staff type, employment status) | Only working doctors hold sessions; suspended doctors' sessions are off |
| `staff_department_assignments` | A doctor must be posted in the department; a posting that ends ends the sessions (signal from the staff domain, like the rota's shifts) |
| `leave_requests` (rotas, HIMS-STAFF-012) | Approved leave takes sessions off; leave asked for shows "Leave asked". The kind of leave is never read out |
| `departments`, `department_hours`, `facilities` | Active department; weekly sessions inside the opening hours; the facility's time zone |

The staff domain calls `scheduling.services.on_employment_status_changed` when employment ends
(sessions end the day before), as it calls the rota's.

## 3. Classification and access

| Data | Level | Who reads it |
|---|---|---|
| Sessions (doctor, department, times, slots) | **Internal** | `appointments.view` for the department (front desk, heads of department, OPD schedulers, administrators); the doctor themself (`/my-opd-sessions/`) |
| Exception reason of a **doctor away** | **Restricted** (personal: why a person is away; "no medical details") | Only `schedules.manage` for the department that recorded it; everyone else sees "Away" |
| Exception reason of a **holiday** or **extra session** | Restricted column, public in practice (e.g. "Diwali") | Everyone who sees the schedule |
| Approved leave from the Leave page | Restricted (its kind) | Never shown here: only "On leave (approved on the Leave page)" |

No patient data is in these tables. `appointments.view` is nonetheless in
`PATIENT_DATA_PERMISSIONS`: once appointments exist (HIMS-OPD-002) the calendar shows booked
patients, so the supplier's support account never holds it.

## 4. Queries and indexes (checked at volume)

| Query | Index | Volume check |
|---|---|---|
| One department's weekly sessions (the week screen) | the department foreign key's index | `opd_department_week` |
| One doctor's sessions (a day's free slots; own sessions; clash check) | `doctor_schedule_staff_idx` (staff, weekday), or the exclusion constraint's index | `opd_doctor_week` |
| A doctor's time away and extra sessions | `schedule_exception_staff_idx` (staff, start date) | `opd_doctor_away` |
| A facility's holidays | `schedule_exception_fac_idx` (facility, start date) | `opd_holidays` |

Screens measured: **Doctor schedules (one department's week)** and **A doctor's free slots on one
day**, both against the 300 ms target, plus the console list (500 ms). Volume: three weekly sessions
per synthetic doctor, two spells away and one extra session each over a year, a holiday a fortnight
([volume check](volume-check.md#doctor-opd-schedules-hims-opd-001)).

## 5. Lifecycle and correction

- **Weekly session:** added (from today or later) → may change slot length, extra bookings, note
  (versioned) → **ended** on a last day (runs that day; `valid_until`), or **withdrawn** before its
  first day (`is_active` off). Days and hours never change: end it and add a new one. Never deleted.
- **Exception:** recorded (from today, at most 400 days ahead, at most 366 days long) → **cancelled**
  with a reason while not over. Past exceptions cannot be cancelled. Never deleted.
- Retention: with the hospital's other operational records (🔒 LEGAL, as for the rota).

## 6. Transactions and concurrency

- One transaction per action, with its audit event (`schedule.session.added|changed|ended`,
  `schedule.exception.added|cancelled`).
- **One doctor at a time:** every change for a doctor locks that doctor's `staff_members` row, so
  two schedulers (or a scheduler and the console) never give one doctor overlapping sessions; for
  weekly sessions the exclusion constraint refuses an overlap even past the service.
- Editable rows carry `version`: a stale change gets 409.
- Several weekdays are added all or none (one transaction).
- Create requests take an `Idempotency-Key` (a double click adds once).

## 7. History

The current rows plus the audit log (before/after). Because a session's days and hours never change
and nothing is deleted, the sessions of any past week can be worked out again exactly (who held
which session, which exceptions applied).

## 8. Migrations

| Migration | What | Notes |
|---|---|---|
| `scheduling.0001_doctor_schedules` | Both tables, their checks, the exclusion constraint and three indexes (with the foreign keys' own) | New, empty tables: no backfill; needs `btree_gist` (made by the rota's migrations, which it depends on) |

## 9. Invariant tests

`apps/scheduling/tests/test_schedule_invariants.py` breaks every database rule on the two tables
directly (past the services) and expects the database to refuse; its last test fails when a table
gains a constraint, unique index or trigger without a test.

## 10. Data flows

None outside HIMS. No email is sent for a schedule change yet; patients booked into affected
sessions are told with HIMS-OPD-002 / 004.

## 11. Review findings (2026-11-15)

| # | Finding | Done |
|---|---|---|
| 1 | A database CHECK passes when a compared value is empty (NULL): "an extra session has slot minutes" and "a timed exception has an end" needed explicit "is not empty" parts | Fixed before the first migration; the invariants test empties each column |
| 2 | Overlap of weekly sessions across departments must be refused for the person, not per department | Exclusion constraint on (doctor, weekday, dates, times); test "even in two departments" |
| 3 | Leave approved on the Leave page must not need entering again | Read from `leave_requests` when a day is worked out (ADR-038) |
| 4 | Why a doctor is away is personal | Shown only to schedule keepers of that department; "Away" for the front desk, in the week, the day and the exceptions list |
| 5 | The doctor's posting or employment ending left sessions running | Ended by the same signals as the rota's shifts |
| 6 | The volume check found the week screen read through the department foreign key's index, never the planned (department, weekday) index | That index dropped before the first release (one index less to keep up) |

## 12. Re-review when

Appointments are added (HIMS-OPD-002: the exclusion constraint on appointments, and sessions that
cannot end or change while patients are booked), walk-ins and tokens (HIMS-OPD-003), or a session
gains a room or a service.

---

# Part 2: Appointments (HIMS-OPD-002)

Phase 2 → Spec §4.6 → Slice 2B. Design: [P0 part 02](../../p0/phase-2-patients/02-database-design.md)
("appointments") and [part 03](../../p0/phase-2-patients/03-state-machines.md) ("Appointment");
decision: [ADR-039](../../decisions/ADR-039-appointments-no-double-booking.md); how-to:
[appointments](../../workflows/appointments.md). Columns and constraints in full: the
[data dictionary](data-dictionary.md) (generated). This is the **Artifact A review** (spec 28.8) of
the `appointments` table, done with the ticket (HIMS-DATA-004).

## A1. Table

| Table | One row is | Key rules (database) |
|---|---|---|
| `appointments` | One patient booked with one doctor in one department, in one session (a weekly session or an extra session), from a start to an end instant, on a day of the facility's clock; new / follow-up; how booked (front desk, phone); status (booked, and from HIMS-OPD-003 checked in, with the doctor, completed, did not come; or cancelled); over the slots or not; who booked it; the appointment it replaced; when, why and by whom it was cancelled | ends after it starts; exactly one session; cancelled exactly when it has when and why; never replaces itself; one appointment is replaced by one other at most; **no two appointments of one doctor overlap** while booked, checked in or with the doctor, except bookings over the slots (`appointment_no_double_booking`, exclusion constraint) |

What P0 part 02 listed and is not here yet: `token_number` (with its unique rule) and `checked_in_at`
come with check-in and walk-ins (HIMS-OPD-003); `service_id` with the clinics of HIMS-OPD-005. Added
beyond P0: the session it was booked into (`schedule` or `extra_session`), so a session's coming
bookings are found directly, and the cancel note.

## A2. Ownership

The outpatient domain writes it (`apps/scheduling/booking.py`); the admin console uses the same
functions. It reads the patients (in use, not merged; restricted), the sessions and everything that
takes them off (part 1, section 2), and the staff row it locks. The rota (Leave page) reads only a
count of a person's bookings during leave waiting for a decision.

## A3. Classification and access

| Data | Level | Who reads it |
|---|---|---|
| An appointment (patient, doctor, department, time, kind, status) | **Clinical** (P0 part 02 "C": it shows which specialty a person sees) | `appointments.view` for the department: front desk, OPD scheduler, head of department, administrators; never the supplier's support account |
| The reason for the visit | Clinical; short, "no detailed history" | The same; hidden with the name for a restricted record |
| A restricted record's appointments (D23) | Clinical, restricted | Name and reason only to people who may open the record (`patients.restricted` or emergency access); others see "Restricted record" and the MRN |
| Who booked, moved, cancelled | Internal (person references) | The same, and the audit log |

Booking, moving and cancelling need `appointments.manage` for the department (front desk, OPD
scheduler) and the right to open a restricted record when the patient's is restricted.

## A4. Queries and indexes (checked at volume)

| Query | Index | Volume check |
|---|---|---|
| A doctor's appointments over some days, put into their sessions (day screen, free slots, doctor's week, extra bookings counted, booking checks) | `appointment_staff_day_idx` (staff, local date), or the exclusion constraint's index | `opd_bookings` |
| One patient's appointments still to come (chart Overview; "already booked at that time") | `appointment_patient_idx` (patient, start) | `patient_appointments` |
| One department's booked appointments still to come (To move) | `appointment_booked_dept_idx` (department, start), partial: booked only | `appointments_to_move` |
| A session's booked days to come (slot length change refused) | the session foreign key's index | — (one session's rows) |
| Every appointment, newest first (console list) | `appointment_start_idx` (start, newest first) | `appointments_newest` |

Screens measured: **Appointments (one department's day)**, **Appointments to move** and **A
patient's upcoming appointments**, plus the console's appointments list. Volume: one million
appointments, five a synthetic doctor a day over two years, the last four weeks still to come
([volume check](volume-check.md#appointments-hims-opd-002)).

## A5. Lifecycle and correction

- **Booked** (from now to 180 days ahead, into an open slot) → **cancelled** with the reason (the
  patient asked / the hospital / the doctor not available) while its day is not over → or **moved**:
  cancelled as "moved to another time" with a link to the appointment that replaced it.
- From HIMS-OPD-003: booked → checked in → with the doctor → completed; booked → did not come (the
  no-show job, undone the same day).
- Never deleted; never edited (a change of time is a move). Retention: with the clinical record
  (🔒 LEGAL).

## A6. Transactions and concurrency

- One transaction per action with its audit event (`appointment.booked`, `.rescheduled`,
  `.cancelled`).
- **Booking locks the doctor's staff row,** so bookings over the slots are counted right and the
  checks see a settled day; the **exclusion constraint** refuses double booking past the service
  (two bookings at the same moment: one gets 409 `SLOT_TAKEN`). Tested with two threads.
- A move is one transaction: the old appointment is cancelled first (its slot frees), then the new
  one is booked; if the new booking fails, the old one stays booked.
- Move and cancel carry `version`; booking takes an `Idempotency-Key`.
- One patient booked with two doctors at the same moment by two people is checked by the service
  only (the two bookings lock different doctors): accepted, see ADR-039.

## A7. History

Every appointment stays, with its links: a moved one points to its replacement, so a patient's
bookings can be followed from the first to the last. The audit log keeps before and after for moves
and the reason for cancellations, never the visit reason's text.

## A8. Migrations

| Migration | What | Notes |
|---|---|---|
| `scheduling.0002_appointments` | The table, its checks, the one-replacement rule, the exclusion constraint and four indexes (with the session foreign key's own) | New, empty table: no backfill; needs `btree_gist` (made by the rota's migrations). Rollback: `migrate scheduling 0001` |

## A9. Invariant tests

`apps/scheduling/tests/test_schedule_invariants.py` now covers the three tables: it breaks every
rule on `appointments` past the service (times, one session, cancelled shapes, moved to itself, two
replacements, version) and books one doctor twice at overlapping times, expecting the database to
refuse; bookings over the slots, after it, or after a cancellation are allowed.

## A10. Data flows

None outside HIMS yet. Emails to patients (booked, moved, cancelled, reminders) come with
HIMS-OPD-004, only with the patient's email consent (D9) and without the specialty in the subject.

## A11. Review findings (2026-11-15)

| # | Finding | Done |
|---|---|---|
| 1 | P0's facility day index (facility, local date, status) made PostgreSQL read a doctor's week through it rather than the doctor's own index; nothing in this ticket needs it | Not added; the To move list got a small partial index (booked only); the facility index comes with the OPD queue (HIMS-OPD-003) |
| 2 | "Cancelled" needed both when and why, and "not cancelled" neither; a CHECK passes on NULL | One CHECK with both shapes; the invariants test breaks each half |
| 3 | Foreign key indexes on a table this size cost every booking (patient, doctor, facility, department, two people) | Off where a composite index leads with the column, or where rows are never looked up by it (people, department, extra session) |
| 4 | A session's slot length changing under booked patients would leave them off their slots | Refused while patients are booked into its coming days (`SESSION_HAS_BOOKINGS`) |
| 5 | Booked patients when a doctor cannot come must not be lost or moved silently | Worked out each time (To move); listed in the exception's answer and counted on the Leave page |
| 6 | A restricted record's name in day lists | "Restricted record" and the MRN unless the reader may open it, in the app and the console |
| 7 | Volume check, first run: the console's appointments list sorted a million rows by day (2.4 s against 500 ms) | Index `appointment_start_idx`; the console list sorts and filters by the start time |
| 8 | Volume check, first run: the To move list of a department whose whole book is off (the synthetic hospital's worst case) took 981 ms, almost all in listing every patient | The list shows the soonest 200 (the next ones appear as these are moved), decided from a few columns and read in full only for those shown: 357 ms; the query itself takes 27 ms |

## A12. Re-review when

Check-in, tokens and the queue arrive (HIMS-OPD-003: the token's unique rule, the facility day
index, the no-show job), reminders are sent (HIMS-OPD-004), clinics gain services or rooms
(HIMS-OPD-005), a waitlist is approved (HIMS-OPD-006), or online booking (Phase 6).
