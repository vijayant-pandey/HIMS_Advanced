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
