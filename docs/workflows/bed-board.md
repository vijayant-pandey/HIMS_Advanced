# Bed board

**Ticket:** HIMS-FAC-008 · **Spec:** 4.10 (real-time availability board; bed states), 15.1 (ward
board in the nurse workspace), 28 (bed status history) · Related:
[locations and beds design](../architecture/data-architecture/locations-and-beds.md)

## In one paragraph

Menu → **Bed board** shows every ward's beds and their status on one screen: a tile per bed with
its type, room, status and how long it has had it, grouped by ward with counts, and "available
now" by bed type. It refreshes every 30 seconds (and when you come back to the tab). Select a bed
to see **why** it is unavailable and its **status history** (from, to, why, who, when), and, if you
manage that ward's beds, to change its status. There are **no patients yet**: admissions, transfers
and discharges fill beds in Phase 3 and will use this same board.

## Who sees what

| Your access (`locations.view`) | You see |
|---|---|
| Hospital-wide or for a facility (administrator, facility administrator, bed manager) | Every active ward of that facility |
| For one department (e.g. a ward nurse with "Basic staff access" for Cardiology) | Only the wards of that department |
| None | The menu item is hidden; the server refuses (403) |

Changing a status needs `beds.status.manage` for the same place (bed manager, facility
administrator). A **department** grant now covers the beds of that department's wards, on the
board and in the bed endpoints. Facilities where Locations is switched off are not shown.

## What is on the screen

| Part | Shows |
|---|---|
| Facility (if you see more than one) | Which facility's board |
| Ward, bed type, "Isolation rooms only" | Filters, applied at once |
| Status chips (All, Available, Maintenance…) | Counts; select one to show only those beds |
| Available now | Free beds by type, e.g. "General 12 · ICU 2" |
| Ward cards | Building, floor, department, men/women and age rules; counts; a tile per bed |
| Bed tile | Code, type, room, isolation, status, "for 3 h" |
| Bed details | Status and reason, the last 20 changes, and the status form if you may change it |

Only active wards, rooms and beds are shown. Switched-off beds are on the Locations page.

## Status history (new table)

`bed_status_changes` keeps one row per change: from, to, reason, who and when. Before this, the
history was only in the audit log, which only auditors may read, so ward staff could not see who
blocked a bed or why. The table is **append-only** (a database trigger refuses changes and
deletes, like the audit log) and the app's own database user cannot alter it
([database users](database-users.md)). Every status change is kept, whoever made it:

- **Change status** on the board, the Locations page or the admin console;
- **switching a bed off** (it becomes "out of service"), in the app or the console.

Changes made before this table existed were copied from the audit log when it was created. The
audit log still records every change too.

## In the admin console

- **Beds → Bed board** (link above the beds list): each ward's beds by status for one facility, and
  the unavailable beds with their reason. Same visibility rules as the app.
- Each bed's page has a **Status history** section; **Bed status changes** lists every change
  (read-only).

## Later (Phase 3)

Reserved, occupied and cleaning come from admissions, transfers, discharges and housekeeping
(spec 4.10). The board will then show the patient's initials only to people allowed to see them,
and update the moment a bed changes (the `bed.status.changed` event already exists for that).

## Tests

- `apps/beds/tests/test_bed_board.py`: every ward with beds, counts and available-by-type;
  switched-off beds left out; a department grant sees only its wards; a department bed manager
  changes only its wards' beds; no access → 403, another facility → 404; facilities with Locations
  off left out; a fixed number of database queries however many beds; history with who and why;
  switching a bed off is kept; console changes kept with who; the database refuses changing or
  deleting history; history visible only where the bed is; earlier changes copied from the audit
  log; the console's bed board, history section and access review schedule.
- `frontend/src/features/locations/BedBoardPage.test.tsx`: wards, counts, available now; filters;
  bed details with history and a status change with its version; read-only for people who cannot
  change it; choosing another facility; empty state; "for 3 h".
- Browser test (`02-hospital-setup`): the board in Chrome with the accessibility check, the reason
  and history of the bed put into maintenance, and putting it back.
