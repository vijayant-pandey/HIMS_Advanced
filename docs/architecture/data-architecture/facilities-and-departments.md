# Data design: facilities and departments (HIMS-FAC-001/002, screens HIMS-FAC-003/006)

Part of **Artifact A — Detailed Data Architecture** (spec 28). Covers the operational rules
(P0-C) for opening and closing facilities and departments. Tables: `facilities`, `departments`
(see migrations; spec 9.2).

## 1. Status
Both have `status` = `active` | `inactive`. Nothing is ever deleted (spec 28.2): closing means
`inactive`, and the row stays for history and for records that point to it.

## 2. Closing in order (HIMS-FAC-006)
Closing something that is still in use would leave staff, access or wards pointing at a place
that no longer operates. So closing happens from the inside out, the same rule as locations
("deactivate everything inside it first"):

| To deactivate… | First finish | Where |
|---|---|---|
| a **department** | current or future staff postings in it | Staff → person → Departments → End |
| | access limited to this department | Access, or Staff → person → Access |
| | active wards that belong to it | Locations → ward → Edit |
| a **facility** | its active departments | Departments |
| | its active buildings | Locations |
| | access given at this facility | Access |

Also:
- A department cannot be **reactivated** while its facility is inactive ("Reactivate the facility
  first").
- New departments and role grants are refused at an inactive facility (existing rules).

The checks live in `Department.clean()` / `Facility.clean()` (code: `apps/facilities/closing.py`),
so the app, the API and the admin console all give the same plain-language message, e.g. *"It
cannot be deactivated yet: 3 staff members are posted here (end their postings on the Staff
page)."*

## 3. What the screens show
- **Facilities:** type, city, time zone, number of **active departments** (links to Departments),
  status, and **Edit**. Editing covers name, type, address, time zone (common zones for the
  country) and status. Code and country never change.
- **Departments** (new menu item): filtered by facility and status. Shows type, facility,
  **current staff** (links to the Staff list filtered to that department), **active wards**,
  status, **Add department** and **Edit** (name, type, status). Codes are set once.
- Every change sends the record's `version`. If someone else changed it first, the save is
  refused and the list refreshes.

## 4. API additions
- `GET /departments/?facility=&status=`; rows include `facility_name`, `department_type_label`,
  `current_staff`, `active_wards`.
- `GET /facilities/`; rows include `facility_type_label` and `active_departments`.
- `GET /staff/?department=`: people posted there now or later.

## 5. Update 2026-10-30: head, services and opening hours (HIMS-FAC-007)

| Table / field | Rules |
|---|---|
| `departments.head` (→ staff member) | Must be a working staff member (active or on leave) **currently posted** in that department. Cleared automatically, with an audit event, when their posting there ends or their employment is terminated. Being head is not a permission: access comes from roles (e.g. "Head of department"). |
| `departments.open_24_hours` | When set, the weekly sessions are ignored (e.g. Emergency, ICU). |
| `department_services` | Name (unique per department, any letter case), description, on/off, `version`. Never deleted. Prices come with billing (Phase 5). |
| `department_hours` | One row per opening session: weekday (0 = Monday), opens, closes, in the **facility's time zone**. Closing must be after opening (database check); sessions on the same day must not overlap; at most 4 per day; a day without sessions is closed. |

The whole week is saved at once (`PUT /departments/{id}/hours/` with the department's `version`).
The old timetable is replaced, and the audit log keeps the full before/after timetable. Timetable
rows are settings, not records of fact, so this is the one place rows are replaced instead of
deactivated. The admin console section does the same (`HimsSettingsInline`, audited).

API: `GET /departments/{id}/` (with services, hours, time zone),
`GET /departments/{id}/head-candidates/`, `PATCH /departments/{id}/` (`head`),
`PUT /departments/{id}/hours/`, `POST /departments/{id}/services/`, `PATCH /department-services/{id}/`.
