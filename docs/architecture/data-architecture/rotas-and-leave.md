# Rotas, on-call and leave (HIMS-STAFF-012)

Spec 4.3 ("employment status, joining/leaving dates, **shift schedules, leave and on-call
rotations**"), 10 (concurrency: the database refuses double booking), 13.2 (least privilege,
separation of duties), 13.4 (audit). All tables live in the hospital's own database (one per
deployment).

## 1. In plain words

- A **head of department** plans who works which **shift** (Morning, Night…) or is **on call**,
  day by day, on the **Rota** page. One week at a time, with "copy last week" to save typing.
- Every member of staff sees their own shifts and leave on **My schedule**, and **asks for
  leave** there.
- An **approver** (head of department, HR officer) approves or refuses leave on the **Leave**
  page. Nobody decides their own leave.
- Anyone with rota access sees **who is on call right now** at the top of the Rota page.

## 2. How it is stored

| Table | Purpose | Key rules |
|---|---|---|
| `shift_types` | The kinds of shift the hospital uses (8 standard ones; the hospital adds its own) | Code never changes; start and end on the facility's clock; an end at or before the start means the shift ends the next day (night); equal times mean 24 hours. Switched off, never deleted. |
| `shifts` | One person on one shift or on call, in one department, starting on one day | `starts_at` / `ends_at` are worked out once from the day, the shift type and the **facility's time zone**, then stored, so later edits to a shift type never move planned shifts. Cancelled with a reason, never deleted. **The database refuses two scheduled shifts for one person that overlap in time** (`shift_no_overlap_per_person`, in any department). |
| `leave_requests` | Time away for one person, and its decision | Kind of leave, first and last day (inclusive), optional note, status **requested → approved / refused**, or **cancelled**; who asked, who decided and when. **The database refuses overlapping leave that is asked for or approved for one person** (`leave_no_overlap_per_person`). |

The two no-overlap rules use PostgreSQL exclusion constraints with the standard `btree_gist`
extension (switched on by the first rota migration). They catch the race the app checks cannot:
two planners booking the same nurse at the same moment.

## 3. Rules

**Planning a shift** (app, API and admin console use the same function, `shift_problem`):

| Refused when | Message names |
|---|---|
| Department not active, or shift type switched off | the reason |
| Person not working (suspended, terminated, on long leave) | the employment status |
| Shift already over | — (past rota is a record; it is not rewritten) |
| Person not posted in that department on that day | the department |
| Person on **approved** leave that day | — |
| Person already has a shift that overlaps (any department) | the other shift |

Planning several days at once (up to 62) or copying a week **skips** the days that cannot be
planned and lists them with the reason, so one problem day does not block the rest.

**Leave:**

- Asked for by the person (My schedule) or recorded for them by an approver (e.g. sick leave
  phoned in, up to 31 days back). Either way it waits for a decision by **someone else**.
- At most 366 days at once; the person must be posted in the department.
- **Approving over planned shifts:** HIMS lists the shifts the person would miss. The approver
  either moves them first or approves with **"cancel those shifts"** (each cancellation audited).
- Refusing needs a reason. The person can withdraw leave until it starts; after that, only an
  approver can end it.
- Emails: approvers when leave is asked for; the person when it is decided or cancelled by
  someone else. Emails hold dates and the kind of leave only.

**Automatic clean-up** (so the rota never shows someone who will not come):

- Suspension, termination or long leave (employment status) cancels the person's future shifts;
  termination also cancels leave that has not started.
- Ending a posting (app or admin console) cancels that person's shifts in that department after
  the posting's last day.

## 4. Who can do what

| Permission | Lets you | Given to (system roles) |
|---|---|---|
| `rota.view` | See a department's rota and who is on call or working now | Basic staff, head of department, HR officer, administrator |
| `rota.manage` | Plan, copy and cancel shifts; with a hospital-wide grant, keep the shift types | Head of department, administrator |
| `leave.approve` | See, approve, refuse, cancel and record leave | Head of department, HR officer, administrator |

All three follow the grant's scope: a head of department's grant covers only their department.
**Privacy:** the rota shows that someone is away, not why. The kind of leave (e.g. sick leave) is
shown only to people who decide leave for that department. Asking for your own leave and seeing
your own schedule need no permission, only a staff record.

## 5. Time zones

Shift times are on the **facility's** clock (each facility has its own time zone), and "today"
for leave is the facility's or the hospital's ([dates and time zones](../../workflows/dates-and-time-zones.md)).
A night shift that crosses a daylight-saving change gets its real length (stored instants).

## 6. Feature setting and admin console

- **Features → Rotas, leave and on-call** (per facility, on by default). When off for a facility,
  its rotas cannot be seen or changed in the app; recorded leave stays.
- Admin console: **Rotas and leave** → shift types (add, rename, switch off), shifts (plan one
  day with the same checks, cancel selected), leave requests (record with the same checks;
  approve, approve and cancel shifts, refuse, cancel selected). Never deleted, every change
  audited.

## 7. Audit events

`rota.shift_type.created`, `rota.shift_type.updated`, `rota.shift.added`,
`rota.shift.cancelled`, `leave.requested`, `leave.approved`, `leave.rejected`,
`leave.cancelled`. Automatic cancellations are recorded with no actor and the reason.

## 8. Not included yet (backlog)

| Ticket | What | Why later |
|---|---|---|
| HIMS-STAFF-013 | Leave balances and entitlements (days per year, carry-over) | Each hospital's HR policy (🔒 PO) |
| HIMS-STAFF-014 | Shift swaps requested by staff, approved by the head | When hospitals ask |
| HIMS-STAFF-015 | Minimum staffing per shift and alerts for gaps | Needs nurse-to-patient rules (🔒 CLIN) |
| Phase 2 | Doctor clinic schedules for appointments | Built on these rotas with the OPD slice (2B) |
| Phase 3 | Nursing shift handover | With nursing (spec 4.9) |
