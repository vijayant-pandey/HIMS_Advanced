# Doctor schedules: OPD sessions, doctors away, holidays and extra sessions (HIMS-OPD-001)

Phase 2 → Spec §4.6 → Slice 2B. Rules: [Phase 2 P0 part 01 §4](../p0/phase-2-patients/01-functional-requirements.md)
("Schedules: per doctor, facility and department: weekday sessions, slot length, maximum extra
bookings, valid from/to; exceptions for leave, holidays and extra sessions"), [part 02](../p0/phase-2-patients/02-database-design.md)
(`doctor_schedules`, `schedule_exceptions`), [part 04](../p0/phase-2-patients/04-roles-and-permissions.md)
(`appointments.view`, `schedules.manage`, the Scheduler role) and P0 decision D11 (extra bookings).
How it works inside: [doctor schedules data design](../architecture/data-architecture/scheduling.md),
[ADR-038](../decisions/ADR-038-opd-sessions-and-free-slots.md).

Booking patients into the slots comes next (HIMS-OPD-002), then walk-ins and the OPD queue
(HIMS-OPD-003) and reminders (HIMS-OPD-004).

**2026-11-15:** booking is built (HIMS-OPD-002): see [appointments](appointments.md). The week now
shows how many patients are booked in each session, and a session's slot length cannot change
while patients are booked into its coming days.

## What it is for

A **session** is a doctor seeing outpatients in one department on one weekday, for example
**every Monday 09:00–13:00 in Cardiology**. It is cut into **slots** (10 minutes unless the
session says otherwise); appointments will be booked into slots. A session may allow a few
**extra bookings** over its slots (D11: none unless set, at most 20).

Three kinds of **exception** change the weekly pattern:

| Exception | What it does | Who records it |
|---|---|---|
| **Doctor away** | Takes that doctor's sessions off, all day or between two times, on one or more days, in every department | Whoever keeps the schedules of a department the doctor is posted in |
| **Holiday** | Closes one department, or the whole facility, for one or more days (or part of a day) | A department: its schedule keeper. **The whole facility: a facility-wide grant** (branch administrator, hospital administrator, or an OPD scheduler given the whole branch) |
| **Extra session** | One more session on one day, with its own slots (e.g. Saturday 14:00–16:00 for a vaccination drive) | The department's schedule keeper |

Sessions are also taken off **by themselves**, without being entered twice:

| When | The session shows |
|---|---|
| Leave **approved on the Leave page** (the rota, HIMS-STAFF-012) | Off: "On leave (approved on the Leave page)". The kind of leave is never shown |
| Leave asked for on the Leave page and **not yet decided** | Still open, with a **Leave asked** chip on that day |
| The doctor is **suspended or on long leave** (Staff page) | Off: "Not working (…)", back on when they return |
| The doctor's **posting in the department ends** | The sessions in that department end on the posting's last day (extra sessions after it are cancelled) |
| The doctor's **employment ends** | Every session ends the day before |
| The **department is closed** (Departments page) | Off |

## Who sees and who changes

| Who | Sees (**Doctor schedules** in the menu) | Changes |
|---|---|---|
| **Head of department** (`schedules.manage` for the department) | Their department | Weekly sessions, doctors away, the department's holidays, extra sessions |
| **OPD scheduler** (new role; department or facility scope) | The departments of the grant | The same; with a facility grant also the facility's holidays |
| **Branch administrator** (Facility administrator) and the **hospital administrator** | Every department of the branch (or hospital) | Everything, including holidays for the whole facility |
| **Front desk** (`appointments.view`) | Every department of the branch: sessions and free slots | Nothing. Why a doctor is away is not shown, only "Away" |
| **Doctors** | Their own sessions on **My schedule** (no permission needed) | Nothing |

The software supplier's support account never holds `appointments.view` (calendars will show
booked patients).

## Add a weekly session

1. **Doctor schedules** → choose the **Department** (and the week with **Previous / This / Next week**).
2. **Add weekly session**: the **Doctor** (doctors posted in the department), the **weekdays**
   (several at once, e.g. Mon, Wed, Fri), **Starts** and **Ends**, **Slot (minutes)** (5–120),
   **Extra bookings per session** (0–20), **From** (today or later), **Until** (optional) and a
   **Note** (e.g. "Room 4"; no patient details). **Add**.
3. The week shows the session on each of those days: "09:00-13:00 · 24 slots". Click it to see its
   free slots.

It is refused, with the reason, when: the person is not a doctor; the doctor is not working or not
posted in the department on the first day; the department is not active; the first day is in the
past; a slot does not fit; the session is outside the department's **opening hours** for that
weekday (when the department has opening hours on the Departments page); or the doctor already has
a session then, **in any department** ("already has a session in Cardiology 09:00-13:00"). Several
weekdays are added all or none.

## Change or end a weekly session

- **Change**: the slot length, the extra bookings and the note.
- **End**: the **last day** it runs (today, a later day, or yesterday to stop it from today), with a
  reason. A last day before its first day withdraws it (it never ran).
- To change the **day or the hours**, end it and add a new one: the old pattern stays on record, so
  any past week can still be shown as it was.

## Record a doctor away, a holiday or an extra session

1. **Doctor away**, **Holiday** or **Extra session**.
2. Doctor away: the **Doctor**, the **First day** (and **Last day** for several days, or **From /
   Until** times for part of one day), **Why?** (e.g. "Conference"; no medical details; only schedule
   keepers see it).
3. Holiday: the days (or part of a day) and **Why?** (e.g. "Diwali"; everyone who sees the schedule
   sees it). Tick **The whole facility** to close every department (only with a facility-wide grant).
4. Extra session: the doctor, the **Day**, **Starts / Ends** and the **Slot**. Refused when the doctor
   already has a session then, is away, or is on approved leave that day.
5. **Record**. The answer lists every session it takes off, all or in part, so you can see at once
   what is affected. (Patients booked in them will be listed there once booking exists, HIMS-OPD-002.)
6. **Cancel** (in **Away, holidays and extra sessions this week**) brings the sessions back, with a
   reason. Past ones cannot be cancelled; nothing is deleted.

## In the admin console

**Doctor schedules (OPD)** → **Doctor schedules** and **Schedule exceptions**, for an administrator
with the console (two-factor): add a session (one weekday at a time) or an exception with the same
rules and messages as the app; change a session's slots, extra bookings or note; **End selected
sessions after today** / **Stop selected sessions from today**; **Cancel selected exceptions**.
Every change is in the audit log (**Audit log** → area **Doctor schedules (OPD)**).

## Turning it off for a facility

**Features** → **Appointments and outpatient visits**, per facility. Off: that facility's doctor
schedules cannot be seen or changed in the app (the admin console still shows them).

## Demo hospitals

Every demo hospital (and the hosted Development hospital after `add_demo_doctor_schedules
--hosted-development`) has, per branch: weekly sessions for the two doctors of each outpatient
department (consultant Mon, Wed, Fri 09:00–13:00; junior doctor Tue, Thu 14:00–17:00), the
cardiologist away 11:00–13:00 next Wednesday, the general physician away three days at a
conference, the paediatrician's extra Saturday session, and a holiday. Sign in as
`opd.<branch>@…` (OPD scheduler), `hod.<branch>@…` (head of Cardiology), `admin.<branch>@…` or
`frontdesk.<branch>@…`. See [demo hospitals](../testing/demo-hospitals.md).

## API

`GET /doctor-schedules/week/?department=&start=` (the week), `GET/POST /doctor-schedules/`,
`PATCH /doctor-schedules/{id}/`, `POST /doctor-schedules/{id}/end/`, `GET/POST /schedule-exceptions/`,
`POST /schedule-exceptions/{id}/cancel/`, `GET /availability/?doctor=&date=` (one doctor's free
slots), `GET /my-opd-sessions/`. Contracts: [endpoints: scheduling](../architecture/api-and-integrations/endpoints/scheduling.md).
