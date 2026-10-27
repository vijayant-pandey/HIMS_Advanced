# Data design: hospital locations and beds (HIMS-FAC-004)

Part of **Artifact A — Detailed Data Architecture** (spec 28). Satisfies the P0-B database design
and P0-C state-machine requirements (spec 26.2, 26.3) for location configuration. Bed
*allocation* (admissions, transfers, the live bed board) is Phase 3 and will extend this design.

**Spec:** 4.1 (wards, floors, rooms, beds, operating rooms), 4.10 (hierarchy, bed types, states,
constraints), 8 (apps `facilities/`, `beds/`), 9.2 (tables `wards`, `rooms`, `beds`), 10 (bed
concurrency), 26.3 (no arbitrary status updates), 28.2 (modelling standards), 28.6 (indexes).

## 1. Hierarchy

```text
Organization (one per deployment)
└── Facility (branch)                         facilities
    └── Building                              buildings
        └── Floor (level: -2 basement … 0 ground … 20)   floors
            └── Ward / Unit (optionally owned by a Department)  wards
                └── Room (incl. operating rooms, ICU bays)    rooms
                    └── Bed                    beds   (app: beds)
```

Each level belongs to exactly one parent. **Parents cannot be changed after creation**: to move a
room or bed, deactivate it and create a new one (history is preserved; spec 28.2 forbids silently
rewriting historical facts). Every row carries `organization_id` and `facility_id` (and beds also
`ward_id`), **derived automatically from the parent on save**, never taken from user input, so
facility-scoped access rules and queries cannot be fooled.

## 2. Tables

All tables: `id` UUID PK, `created_at`, `updated_at`, `version` (optimistic concurrency), foreign
keys `ON DELETE PROTECT`, no deletion through API or admin console (deactivate instead).

### buildings
| Column | Type | Null | Notes |
|---|---|---|---|
| organization_id | FK organizations | no | derived |
| facility_id | FK facilities | no | parent |
| code | slug(32) | no | unique per facility |
| name | varchar(255) | no | |
| is_active | bool | no | default true |

### floors
| Column | Type | Null | Notes |
|---|---|---|---|
| organization_id, facility_id | FK | no | derived from building |
| building_id | FK buildings | no | parent |
| level | smallint | no | -5 … 200; unique per building |
| name | varchar(100) | no | e.g. "Ground floor", "Level 2" |
| is_active | bool | no | |

### wards
| Column | Type | Null | Notes |
|---|---|---|---|
| organization_id, facility_id | FK | no | derived from floor |
| floor_id | FK floors | no | parent |
| department_id | FK departments | yes | owning department; must be in the same facility |
| code | slug(32) | no | unique per facility |
| name | varchar(255) | no | |
| ward_type | enum | no | general, private, icu, hdu, nicu, picu, emergency, maternity, isolation, day_care, operating_theatre, recovery |
| gender_restriction | enum | no | any (default), male, female |
| age_group | enum | no | any (default), adult, pediatric, neonatal |
| is_active | bool | no | |

### rooms
| Column | Type | Null | Notes |
|---|---|---|---|
| organization_id, facility_id | FK | no | derived from ward |
| ward_id | FK wards | no | parent |
| code | slug(32) | no | unique per ward (e.g. `201`, `icu-bay-a`) |
| name | varchar(255) | no | |
| room_type | enum | no | general, private, semi_private, icu_bay, isolation, operating_room, procedure, recovery, consultation |
| is_isolation_capable | bool | no | e.g. negative-pressure room (infection control, spec 4.10/4.12) |
| is_active | bool | no | |

### beds (app `beds`)
| Column | Type | Null | Notes |
|---|---|---|---|
| organization_id, facility_id, ward_id | FK | no | derived from room |
| room_id | FK rooms | no | parent |
| code | slug(32) | no | unique per ward (bed labels like `B1`, `ICU-03`) |
| bed_type | enum | no | general, semi_private, private, deluxe, icu, hdu, nicu, picu, isolation, day_care, labour, recovery, emergency_trolley |
| status | enum | no | see §3; default `available` |
| status_reason | varchar(255) | yes | required for maintenance/blocked/out_of_service |
| status_changed_at | timestamptz | no | |
| is_active | bool | no | inactive beds must be `out_of_service` (check constraint) |

### Constraints and indexes (spec 28.6)
| Table | Constraint / index | Why |
|---|---|---|
| buildings | unique (facility, code) | stable codes per branch |
| floors | unique (building, level); check level between -5 and 200 | one row per level |
| wards | unique (facility, code) | ward codes appear on wristbands/boards |
| rooms | unique (ward, code) | |
| beds | unique (ward, code) | bed labels unique within a ward |
| beds | check: `is_active` or `status = 'out_of_service'` | a decommissioned bed can never look usable |
| beds | index (facility, ward, status) | "beds by facility/ward/status" (bed board) |
| beds | index (facility, bed_type, status) | "compatible bed type" search |
| wards | index (facility, ward_type) | ICU/NICU lookups |

Department-to-ward consistency (same facility) and "parent must be active to add children" are
enforced in model validation, which both the API and the admin console run.

## 3. Bed status state machine (P0-C)

```text
                       (Phase 3: admission/ADT workflow)
         ┌───────────── reserved ──────────────┐
         │                                     ▼
   available ──────────────────────────────► occupied ──► cleaning ──► available
     ▲  │ ▲                                                 (housekeeping sign-off, Phase 3)
     │  │ └──────────────┐
     │  ▼                │
  maintenance ◄──► blocked ◄──► out_of_service
     (configuration / operations: this release)
```

| Current state | Requested action | Guard | Actor (permission) | Next state | Audit event | Outbox event |
|---|---|---|---|---|---|---|
| available, maintenance, blocked, out_of_service | set status | target is one of available/maintenance/blocked/out_of_service; reason required unless target is available; current `version` matches; bed active (or target out_of_service) | `beds.status.manage` at the bed's facility | target | `bed.status.changed` | `bed.status.changed` |
| occupied, reserved, cleaning | set status | **refused** (409 `BED_STATUS_MANAGED_BY_ADT`): these states belong to admission, transfer, discharge and housekeeping workflows (Phase 3) | — | — | `access.denied`/error | — |
| any | deactivate bed | bed not occupied/reserved | `locations.manage` | out_of_service, is_active=false | `bed.updated` | — |

Status changes lock the bed row (`SELECT … FOR UPDATE`) and check the version, so two people
changing the same bed at once cannot overwrite each other (spec 10). Phase 3 adds bed
*assignments* (time-bounded, at most one active per bed via a partial unique index) and the
reserved/occupied/cleaning transitions.

## 4. Permissions (spec 26.4)

| Permission | Meaning | Two-factor required |
|---|---|---|
| `locations.view` | See buildings, floors, wards, rooms, beds | no |
| `locations.manage` | Create/edit/deactivate locations and beds | yes (structural configuration) |
| `beds.status.manage` | Put beds into/out of maintenance, blocked, out of service | no (frequent operational task) |

Granted by system roles: Organization administrator (all), Facility administrator (all three, at
its facility), new **Bed manager / ward clerk** role (`locations.view` + `beds.status.manage`),
Head of department and Basic staff access (`locations.view`).

## 5. Data ownership and retention

Owner: facility/locations domain (spec 28.3: "Bed occupancy — bed assignment domain" in Phase 3).
Locations are configuration, not patient data (no PHI). Rows are never deleted; inactive rows stay
for history and future references from bed assignments.

## 6. API (contract: `docs/api/openapi.yaml`)

| Endpoint | Permission | Notes |
|---|---|---|
| `GET/POST /api/v1/buildings/`, `GET/PATCH /buildings/{id}/` | view / manage | filter `?facility=`, `?active=true` |
| `GET/POST /floors/`, `GET/PATCH /floors/{id}/` | view / manage | filter `?building=`, `?facility=` |
| `GET/POST /wards/`, `GET/PATCH /wards/{id}/` | view / manage | filter `?floor=`, `?ward_type=`, `?department=` |
| `GET/POST /rooms/`, `GET/PATCH /rooms/{id}/` | view / manage | filter `?ward=`, `?room_type=` |
| `GET/POST /beds/`, `GET/PATCH /beds/{id}/` | view / manage | filter `?ward=`, `?room=`, `?status=`, `?bed_type=` |
| `POST /beds/bulk/` | manage | e.g. prefix `b`, count 4 → `b01`…`b04` (max 60, all or nothing) |
| `POST /beds/{id}/status/` | `beds.status.manage` | body `{version, status, reason}`; reason required unless `available` |
| `GET /facilities/{id}/locations/` | view | whole tree in one request with bed counts per ward and facility |

All creates accept `Idempotency-Key`. Edits need the current `version` (stale → 409). Nothing is
deleted: send `is_active: false`. Parents and codes cannot be changed after creation. Records
outside the user's facility scope return 404. The admin console offers the same (parents read-only
when editing; bed status only through the "Mark available / out of service" actions).
