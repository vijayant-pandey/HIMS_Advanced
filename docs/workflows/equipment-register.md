# Equipment register (HIMS-FAC-009)

**Spec:** 4.12 "equipment inventory, maintenance and calibration", 4.2 department equipment.

The register answers four questions about anything the hospital owns: **what** it is, **where** it
is, whether it **can be used**, and **when** it is next due for service or calibration.

Only the register is built. Service requests, job orders, wheelchair and stretcher transport and
automatic reminders are workflows that wait for the product owner's decision (spec 4.12, 4.23).

## Using it

Menu → **Equipment**.

| To do this | Do this |
|---|---|
| Find something | Search by tag, name, serial or maker; filter by facility, status, category or **Due** |
| Add an item | **Add equipment**. The **asset tag** is the number on the label; it is set once and written in capitals. Another facility may use the same number |
| See its details and visits | Select its asset tag |
| Take it out of use | Select it → **Change status**. Anything except **In service** needs a reason, e.g. "Battery fault". No patient details |
| Record a service, repair or calibration | Select it → **Record a visit**, with the date, who did it and when the next one is due |
| Print the list | **Print**. The paper has the hospital's [letterhead](letterhead.md) and no menu or buttons. It prints the page on screen (100 items per page), so filter first if the list is long |

## What "Due" means

- **Overdue:** the service or calibration date has passed. The earlier of the two dates decides.
- **Due in 30 days:** one of them falls within the next 30 days.
- Retired equipment is never due. "Today" is the hospital's today
  ([dates and time zones](dates-and-time-zones.md)).

## Visits

- The newest visit sets **Last service** and **Next service due** (or the calibration dates).
- A repair counts with services. Only a calibration sets the calibration dates.
- An older visit entered late joins the history without moving the dates.
- **A visit cannot be changed or deleted, even directly in the database** (the same trigger as the
  audit log). To correct a mistake, add another visit.
- A retired item takes no visits: bring it back into use first.
- If a date on the register itself is wrong, correct it with **Edit**. The change is in the audit
  log.

## Who can do what

| Permission | Allows | Held by |
|---|---|---|
| `equipment.view` | See the register and visits | Organization administrator, facility administrator, head of department, equipment officer |
| `equipment.manage` | Add, edit, change status, record visits | Organization administrator, facility administrator, equipment officer |

- A new system role, **Equipment / biomedical officer**, keeps the register. Give it at facility or
  department level.
- A **department-level** grant sees and changes only what is registered to that department, and can
  add only to that department. Items with no department need a facility-level grant.

## Switching it off

**Features → Equipment register** can switch it off for one facility. Its items then leave the list
and cannot be opened or added in the app. The admin console still shows them.

## Admin console

- **Equipment:** the same list with a filter for overdue and due-soon items, the same status rules
  and a **Last visits** section on each item.
- **Equipment service records:** add a visit under the same rules. Existing visits are read-only.
- Asset tag and facility cannot change after the item is added.

## Tables

`equipment` and `equipment_service_records` (append-only). Columns and classifications:
[data dictionary](../architecture/data-architecture/data-dictionary.md).
