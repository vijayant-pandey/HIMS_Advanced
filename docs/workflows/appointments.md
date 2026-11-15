# Appointments: booking, moving and cancelling (HIMS-OPD-002)

Phase 2 → Spec §4.6 → Slice 2B. Rules: [Phase 2 P0 part 01 §4 and §10](../p0/phase-2-patients/01-functional-requirements.md)
("Booking: choose department → doctor → day → free slot → patient → type (new / follow-up) → reason
(short). Rescheduling keeps a link to the old appointment. Cancellation needs a reason. Booking a
slot that is already taken is refused, even if two people try at the same moment"),
[part 02](../p0/phase-2-patients/02-database-design.md) (`appointments`, "no double booking
(database guarantee)"), [part 03](../p0/phase-2-patients/03-state-machines.md) ("Appointment"),
[part 04](../p0/phase-2-patients/04-roles-and-permissions.md) (`appointments.manage`) and P0
decision D11 (extra bookings). How it works inside: [data design, part 2](../architecture/data-architecture/scheduling.md#part-2-appointments-hims-opd-002),
[ADR-039](../decisions/ADR-039-appointments-no-double-booking.md). The sessions and slots come from
[doctor schedules](doctor-schedules.md) (HIMS-OPD-001).

Check-in, walk-ins, tokens and the OPD queue come next (HIMS-OPD-003), then email reminders
(HIMS-OPD-004). **2026-11-15, HIMS-OPD-003 done:** the day of the visit (check-in with tokens,
walk-ins, Call next, did not come) is on the [OPD queue](opd-queue.md); the day's list here shows
each patient's token next to their status.

## Who does what

| Person | Can | Permission |
|---|---|---|
| Front desk (Receptionist role) | Book, move and cancel in every department of their branch; find patients; register new ones | `appointments.manage` (+ `appointments.view`, patient permissions) |
| OPD scheduler | Book, move and cancel in their department or branch; find patients by the short list (not open the record); keep the doctors' sessions | `appointments.manage`, `patients.search`, `schedules.manage` |
| Head of department | See the day's appointments and the patients to move in their department; keep the sessions (does not book) | `appointments.view`, `schedules.manage` |
| Branch and hospital administrators | See appointments (do not book: the front desk does, P0 part 04) | `appointments.view` |
| Medical records | Book a **restricted** record's patient (others see "Restricted record") | `patients.restricted` with a booking role |
| Doctor | See how many patients are booked in their own sessions on **My schedule** | — |

## Book a patient

1. Open **Appointments** in the menu (or a patient's chart and press **Book**: the patient is
   chosen already).
2. Choose the **department** and the **day** (Previous day / Today / Next day, or type a date).
   Each doctor's sessions that day show their slots: green ones are free, grey ones say "booked".
   Slots that have passed are counted, not shown.
3. Press a free slot (for example **09:10**). In the dialog:
   - **Find the patient** by MRN, phone, ID number or name, press **Search**, then pick the
     patient. Nobody found: register them on the Patients page first. (Each search is in the audit
     log, as on the Patients page.)
   - **Visit:** New or Follow-up. **Booked:** at the front desk or by phone.
   - **Reason (optional):** short, for example "Blood pressure review". No detailed history.
4. Press **Book**. The slot shows "booked" and the patient is in the day's list below.

### Over the slots (extra bookings)

When a session allows extra bookings (D11, set on the Doctor schedules page) and some slots are
booked, **Book over the slots (N left)** appears under the session. It books one more patient into
a slot that is already booked. A free slot is always booked normally.

### What is refused, and why

| You see | Because |
|---|---|
| "This slot is already booked: choose another (or book over the slots, N left)" | Someone booked it before you; choose another slot |
| "This slot was just taken: choose another" | Two people pressed Book at the same moment: the database let only one through |
| "… is not a free slot of this session: Away" (or Holiday, On leave…) | The doctor is away, on leave or the department is closed then |
| "This time has already passed" / "at most 180 days ahead" | Appointments are from now to six months ahead |
| "The patient is already booked with Dr … at …" | One patient cannot be in two places at once |
| "This record was merged into another one" | Book on the record it was merged into |
| "This is a restricted record" | Only medical records (or emergency access) may act on it |

## Move or cancel an appointment

In the day's list (or the **To move** list), each booked patient has **Move** and **Cancel**:

- **Move:** choose the new day, the doctor (the same unless changed) and a free slot; add why
  (optional). The old appointment stays in the list as **Cancelled (Moved to another time)** and
  links to the new one.
- **Cancel:** choose why (the patient asked / the hospital cancelled / the doctor is not available),
  add a note if useful. It stays in the list as cancelled, and its slot is free again. An
  appointment whose day is over cannot be cancelled (missed appointments are marked with the OPD
  queue, HIMS-OPD-003).

## When the doctor cannot come: To move

Nothing is cancelled by itself. When a doctor is recorded **away**, a **holiday** is recorded, leave
is **approved on the Leave page**, or a session **ends**, every booked patient still to come in the
time it takes off appears at the top of the Appointments page under **To move**, with why ("Away",
"Holiday: Diwali", "On leave (approved on the Leave page)", "The session no longer runs that day").
Move or cancel each one; the list empties as you go.

- Recording **Doctor away** or a **Holiday** on the Doctor schedules page answers with the booked
  patients it hits, straight away.
- On the **Leave** page, leave waiting for a decision says how many OPD patients are booked during
  it, so the approver knows before approving.
- Why a doctor is away is shown only to the people who keep the schedules; the front desk sees
  "Away".
- A session's **slot length** cannot be changed while patients are booked into its coming days:
  move them first, or end the session and add a new one.

## In the chart and on My schedule

- The chart's **Overview** shows the **next appointment** (day, time, doctor, department, and how
  many more), for people who see appointments.
- The chart header has **Book** for the front desk and OPD schedulers.
- Doctors see on **My schedule** how many patients are booked in each of their sessions.

## In the admin console

**Doctor schedules (OPD) → Appointments:** the list (filter by status, kind, facility, department,
day; search by exact MRN; restricted records show only their MRN to people who may not open them).

- **Add appointment** books with the same rules (the time is a free slot's start on the facility's
  clock).
- An appointment's page has **Move to another time** (its own page, same rules).
- Actions **Cancel selected: the patient asked / the hospital cancelled / the doctor is not
  available**.
- **Appointments to move** (top right) lists the department's patients to move, with **Move** links.
- A patient's console page shows their **upcoming appointments** in the Chart section.

Every booking, move and cancellation is in the audit log (area **Appointments (OPD)**).

## Demo hospitals

Each branch has, in the cardiologist's first session with free slots in the next two weeks: booked
patients (new and follow-up), one moved later, one cancelled, one over the slots; and an obstetrics
patient whose doctor was then called away (on the To move list). Sign in as `frontdesk.<branch>@`
or `opd.<branch>@` to book, `hod.<branch>@` to look. The hosted Development hospital gets them with
`add_demo_appointments --hosted-development` ([hosting](render-neon-hosting.md)).
