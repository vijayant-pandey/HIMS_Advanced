# Requirement records: hospital, facilities, locations, numbering and features

Spec sections 4.1, 4.2, 4.10, 4.12, 9.2. Format: [README](README.md). Endpoints:
[hospital settings](../architecture/api-and-integrations/endpoints/organizations.md),
[facilities and locations](../architecture/api-and-integrations/endpoints/facilities.md),
[beds](../architecture/api-and-integrations/endpoints/beds.md),
[equipment](../architecture/api-and-integrations/endpoints/equipment.md),
[numbering](../architecture/api-and-integrations/endpoints/numbering.md),
[features](../architecture/api-and-integrations/endpoints/features.md).

## Hospital (organization)

### HIMS-ORG-001

| Field | Record |
|---|---|
| ID and title | HIMS-ORG-001 One organization per deployment, created only by `provision_organization` (ADR-009) |
| Business/clinical reason | Each hospital gets its own deployment and database (spec 7); the hospital record must exist once, with its country, time zone and currency fixed at setup. Owner: PO |
| Actors | The person deploying HIMS (command line, database owner); nobody through the API |
| Preconditions | Empty, migrated database |
| Main success path | `python manage.py provision_organization` creates the organization, the system roles and the first administrator with an invitation |
| Alternate/failure paths | A second organization is refused; missing country, time zone or currency is refused; running it again changes nothing |
| Data effects | `organizations`, `roles`, `role_permissions`, `users`, `user_invitations` |
| Security classification | Configuration (internal) |
| Audit requirement | `organization.provisioned`, `user.created`, `user.invitation.issued` |
| Idempotency/concurrency | One row per deployment, enforced by the command and a database check |
| Integration dependencies | Email for the first invitation (console locally; HIMS-OPS-011 at hosting) |
| Acceptance criteria | Exactly one organization; API callers can read but never create one; IN and US deployments run side by side with separate data |
| Test evidence | `apps/organizations/tests/test_organization.py`; browser tests set up both deployments (`frontend/e2e/config.mjs`); manual test Parts 1 and 21 |
| Release risk | Operational: a wrong country or currency needs a new deployment. Rollback: drop the empty database and provision again |

### HIMS-ORG-002

| Field | Record |
|---|---|
| ID and title | HIMS-ORG-002 `GET/PATCH /organization/` with versioning and audit |
| Business/clinical reason | Administrators keep the hospital's names and default time zone correct without a developer. Owner: PO |
| Actors | `organization.view` to read, `organization.manage` to change (Organization administrator) |
| Preconditions | Organization provisioned |
| Main success path | Read the settings; change name, legal name or default time zone sending the `version` read |
| Alternate/failure paths | Stale `version` → 409 `STALE_RESOURCE`; country and currency cannot be changed (400) |
| Data effects | `organizations` (one row) |
| Security classification | Configuration (internal) |
| Audit requirement | `organization.updated` with the changed fields |
| Idempotency/concurrency | `version` check and row lock |
| Integration dependencies | None |
| Acceptance criteria | Two administrators editing at once: the second save is refused, nothing overwritten; every change in the audit log |
| Test evidence | `apps/organizations/tests/test_organization.py`; browser test `02-hospital-setup.spec.ts`; manual test Part 2 |
| Release risk | Low. Rollback: change the values back (audited) |

### HIMS-ORG-003

| Field | Record |
|---|---|
| ID and title | HIMS-ORG-003 Hospital-specific numbering schemes (medical record, visit, invoice, claim numbers) |
| Business/clinical reason | Each hospital has its own number formats; a number must never be issued twice, as two patients or two invoices sharing one is a clinical and financial hazard. Owner: PO |
| Actors | `numbering.view`, `numbering.manage` (whole hospital or one facility); the future patient and billing workflows issue numbers |
| Preconditions | Organization; facilities for facility-level schemes |
| Main success path | Set prefix, padding, reset period and next number, try it with Preview, save; numbers are issued in order and recorded |
| Alternate/failure paths | Invalid pattern → 400 with the problem; moving the next number backwards → 409; a missing scheme when a number is needed → `NUMBERING_NOT_CONFIGURED` |
| Data effects | `numbering_schemes`, `numbering_counters`, `issued_numbers` |
| Security classification | Configuration (internal) |
| Audit requirement | `numbering.scheme.created`, `numbering.scheme.updated`, `numbering.next_number.set` |
| Idempotency/concurrency | Row lock on the counter plus a unique index on issued numbers (six-thread test); Idempotency-Key on writes |
| Integration dependencies | None |
| Acceptance criteria | Parallel issuing never repeats a number; changes audited; the Numbering page shows an example before saving |
| Test evidence | `apps/numbering/tests/test_numbering.py`; manual test Part 6 |
| Release risk | Financial and clinical if numbers repeat (prevented by the database). Rollback: settings can be changed; issued numbers are never reused |

### HIMS-ORG-004

| Field | Record |
|---|---|
| ID and title | HIMS-ORG-004 Feature settings per hospital, country and facility (ADR-019) |
| Business/clinical reason | Parts of HIMS are switched on per hospital or branch; country-only features (ABDM) must never appear elsewhere. Owner: PO |
| Actors | `features.view`, `features.manage`; every signed-in screen reads the effective settings |
| Preconditions | Organization |
| Main success path | Turn a feature on, off or back to the default for the hospital or one facility; screens and the API follow at once |
| Alternate/failure paths | A feature not offered in the country cannot be turned on; a switched-off feature's endpoints answer `FEATURE_DISABLED` |
| Data effects | `feature_flags` |
| Security classification | Configuration (internal) |
| Audit requirement | `feature.flag.changed` |
| Idempotency/concurrency | One setting per feature and scope (unique rule); repeating a change is harmless |
| Integration dependencies | None |
| Acceptance criteria | Turning off Locations hides the screens and refuses the endpoints; US hospitals never see India-only features as "coming" |
| Test evidence | `apps/features/tests/test_features.py`; browser tests `02-hospital-setup.spec.ts`, `us/01-us-hospital.spec.ts`; manual test Part 14 |
| Release risk | Operational: a feature switched off by mistake hides a screen. Rollback: switch it back |

### HIMS-ORG-005

| Field | Record |
|---|---|
| ID and title | HIMS-ORG-005 Hospital settings screen (name, legal name, default time zone) |
| Business/clinical reason | Non-developers keep the hospital's details correct. Owner: PO |
| Actors | `organization.view`, `organization.manage` |
| Preconditions | Organization provisioned |
| Main success path | Hospital settings page shows the details; Edit saves with the `version` |
| Alternate/failure paths | Stale version → the page says someone else changed it; read-only users see no Edit button |
| Data effects | `organizations` |
| Security classification | Configuration (internal) |
| Audit requirement | `organization.updated` |
| Idempotency/concurrency | As HIMS-ORG-002 |
| Integration dependencies | None |
| Acceptance criteria | Changes show at once on the page and in the audit log; country and currency shown but fixed |
| Test evidence | `apps/organizations/tests/test_organization.py`; frontend `OrganizationSettingsPage` tests; manual test Part 2 |
| Release risk | Low. Rollback: edit back |

### HIMS-ORG-006

| Field | Record |
|---|---|
| ID and title | HIMS-ORG-006 Hospital logo and letterhead for printouts and emails |
| Business/clinical reason | Printouts and emails carry the hospital's own name, address and logo (spec 4.1). Owner: PO |
| Actors | `organization.manage` to change the logo; anyone signed in to see it (no public URL) |
| Preconditions | Organization; virus scanner reachable for uploads |
| Main success path | Upload a PNG or JPEG; it is checked for viruses, stored and used on the letterhead and in emails |
| Alternate/failure paths | Wrong type or too large → 400; virus → refused and audited (`upload.blocked`); scanner down → `SCANNER_UNAVAILABLE`, nothing stored |
| Data effects | `organizations.logo`; file storage |
| Security classification | Configuration (internal) |
| Audit requirement | `organization.logo.changed`, `upload.blocked` |
| Idempotency/concurrency | Replacing the logo is last-write-wins on one field; each change audited |
| Integration dependencies | Virus scanner (HIMS-SEC-013); file storage (local; S3-compatible at hosting, HIMS-OPS-015) |
| Acceptance criteria | No logo without sign-in; letterhead shows hospital and facility details; removing the logo falls back to the name |
| Test evidence | `apps/organizations/tests/test_letterhead.py`; manual test Part 18i |
| Release risk | Low. Rollback: remove or replace the logo |

## Facilities and departments

### HIMS-FAC-001

| Field | Record |
|---|---|
| ID and title | HIMS-FAC-001 Facilities API: list, create, open, change; scoped visibility; audit |
| Business/clinical reason | A hospital group runs several branches; each person sees only the branches they are granted (spec 4.1, 13.2). Owner: PO |
| Actors | `facilities.view`; `facilities.manage` (organization-wide to create) |
| Preconditions | Organization provisioned |
| Main success path | Add a facility with code, type, address and time zone; list shows only facilities in the caller's scope |
| Alternate/failure paths | Duplicate code → 409 `DUPLICATE_CODE`; invalid time zone → 400; facility-scoped user creating → 403; out-of-scope facility → 404 |
| Data effects | `facilities` |
| Security classification | Configuration (internal) |
| Audit requirement | `facility.created`, `facility.updated`; refusals `access.denied` |
| Idempotency/concurrency | Optional Idempotency-Key on create; `version` on change |
| Integration dependencies | None |
| Acceptance criteria | A branch administrator never sees another branch; the same create with the same key creates one facility |
| Test evidence | `apps/facilities/tests/test_facilities_api.py`, `apps/access_control/tests/test_authorization.py`, `common/tests/test_idempotency.py`; manual test Part 3 |
| Release risk | Privacy if scope leaked (tested both ways). Rollback: deactivate the facility |

### HIMS-FAC-002

| Field | Record |
|---|---|
| ID and title | HIMS-FAC-002 Departments API: created within facility scope; no departments in inactive facilities |
| Business/clinical reason | Departments organize staff, rotas and wards inside a facility (spec 4.2). Owner: PO |
| Actors | `departments.view`, `departments.manage` (facility-scoped) |
| Preconditions | An active facility |
| Main success path | Add a department to a facility in scope; list and open within scope |
| Alternate/failure paths | Inactive facility → 409; out of scope → 403/404; duplicate code in the facility → 409 |
| Data effects | `departments` |
| Security classification | Configuration (internal) |
| Audit requirement | `department.created`, `department.updated` |
| Idempotency/concurrency | Optional Idempotency-Key; `version` on change |
| Integration dependencies | None |
| Acceptance criteria | Cannot add a department to a closed facility; a facility admin cannot touch another facility's departments |
| Test evidence | `apps/facilities/tests/test_departments_and_closing.py`; manual test Part 4 |
| Release risk | Low. Rollback: deactivate |

### HIMS-FAC-003

| Field | Record |
|---|---|
| ID and title | HIMS-FAC-003 Facilities screen (list and create, with idempotency) |
| Business/clinical reason | Administrators add branches without a developer. Owner: PO |
| Actors | `facilities.view`, `facilities.manage` |
| Preconditions | Organization provisioned |
| Main success path | Facilities page lists branches; Add facility sends an Idempotency-Key so a double click creates one |
| Alternate/failure paths | Validation errors shown per field; a new facility defaults to the hospital's country and time zone (US fix in HIMS-QA-003) |
| Data effects | `facilities` |
| Security classification | Configuration (internal) |
| Audit requirement | `facility.created` |
| Idempotency/concurrency | Idempotency-Key per dialog |
| Integration dependencies | None |
| Acceptance criteria | Double submit creates one facility; errors appear next to the field |
| Test evidence | Frontend `CreateFacilityDialog.test.tsx`; browser test `02-hospital-setup.spec.ts`; manual test Part 3 |
| Release risk | Low |

### HIMS-FAC-004

| Field | Record |
|---|---|
| ID and title | HIMS-FAC-004 Location hierarchy: building → floor → ward → room → bed (configuration; allocation comes with admissions) |
| Business/clinical reason | Beds must be known and countable before patients can be admitted (spec 4.10, 10.1). Owner: PO; bed rules CLIN |
| Actors | `locations.view`, `locations.manage`; `beds.status.manage` (bed manager) |
| Preconditions | Facility; Locations feature on |
| Main success path | Add the hierarchy; set bed status (available, cleaning, maintenance, blocked) with a reason |
| Alternate/failure paths | Occupied and reserved can only be set by the future admission workflow (`BED_STATUS_MANAGED_BY_ADT`); missing reason → `STATUS_REASON_REQUIRED`; codes are locked after creation; stale version → 409 |
| Data effects | `buildings`, `floors`, `wards`, `rooms`, `beds`, `bed_status_changes`; outbox `bed.status.changed` |
| Security classification | Configuration (internal) |
| Audit requirement | `location.created`, `location.updated`, `bed.status.changed` |
| Idempotency/concurrency | Row lock and `version` on bed status; Idempotency-Key on creates |
| Integration dependencies | None |
| Acceptance criteria | Two people changing one bed at once: one wins, the other gets 409; nothing can mark a bed occupied by hand |
| Test evidence | `apps/beds/tests/test_locations_and_beds.py`; manual test Part 5 |
| Release risk | Clinical later (bed availability); none now. Rollback: deactivate locations |

### HIMS-FAC-005

| Field | Record |
|---|---|
| ID and title | HIMS-FAC-005 Screens to add and edit buildings, floors, wards, rooms and beds |
| Business/clinical reason | Hospital staff set up their own locations. Owner: PO |
| Actors | `locations.view`, `locations.manage` |
| Preconditions | HIMS-FAC-004 |
| Main success path | Locations page tree; add, edit and deactivate at each level; add many beds at once |
| Alternate/failure paths | Deactivating a parent with active children is refused; bulk add limited to 60 beds |
| Data effects | As HIMS-FAC-004 |
| Security classification | Configuration (internal) |
| Audit requirement | `location.created`, `location.updated` |
| Idempotency/concurrency | Idempotency-Key on creates; `version` on edits |
| Integration dependencies | None |
| Acceptance criteria | A ward of 30 beds can be added in one step; everything audited |
| Test evidence | `apps/beds/tests/test_locations_and_beds.py`; browser test `02-hospital-setup.spec.ts`; manual test Part 5 |
| Release risk | Low |

### HIMS-FAC-006

| Field | Record |
|---|---|
| ID and title | HIMS-FAC-006 Departments screen and facility edit screen; close in order |
| Business/clinical reason | Closing a facility or department must not leave staff, wards or rotas pointing at it. Owner: PO |
| Actors | `facilities.manage`, `departments.manage` |
| Preconditions | Facilities and departments exist |
| Main success path | Edit and deactivate from the screens; closing happens bottom-up |
| Alternate/failure paths | Closing a facility with open departments, or a department with active postings, is refused with what to close first |
| Data effects | `facilities`, `departments` |
| Security classification | Configuration (internal) |
| Audit requirement | `facility.updated`, `department.updated` |
| Idempotency/concurrency | `version` checks |
| Integration dependencies | None |
| Acceptance criteria | Nothing open is orphaned; the refusal says what blocks it |
| Test evidence | `apps/facilities/tests/test_departments_and_closing.py`; manual test Part 4 |
| Release risk | Low. Rollback: reactivate |

### HIMS-FAC-007

| Field | Record |
|---|---|
| ID and title | HIMS-FAC-007 Department head, services offered and opening hours |
| Business/clinical reason | Departments publish who leads them, what they offer and when they are open (spec 4.2). Owner: PO |
| Actors | `departments.manage` for the department |
| Preconditions | Department; head candidates are staff posted to it |
| Main success path | Choose a head from posted staff; add services; set weekly hours or open 24 hours |
| Alternate/failure paths | Head not posted there → 400; overlapping hours → 400; stale version → 409 |
| Data effects | `departments`, `department_services`, `department_hours` |
| Security classification | Configuration (internal) |
| Audit requirement | `department.updated`, `department.service.created`, `department.service.updated`, `department.hours.changed` |
| Idempotency/concurrency | `version` on department; hours replaced as one set |
| Integration dependencies | None |
| Acceptance criteria | Hours replaced atomically; only posted staff can be head |
| Test evidence | `apps/facilities/tests/test_department_details.py`; manual test Part 10 |
| Release risk | Low |

### HIMS-FAC-008

| Field | Record |
|---|---|
| ID and title | HIMS-FAC-008 Bed board: every ward's beds and status on one screen (no patients yet) |
| Business/clinical reason | Bed managers see free, cleaning and blocked beds at a glance (spec 4.10). Owner: PO |
| Actors | `locations.view` (department grants see their own wards); `beds.status.manage` to change |
| Preconditions | Locations set up |
| Main success path | Bed board shows counts per ward; open a bed to see its last 20 status changes |
| Alternate/failure paths | Out-of-scope wards hidden; feature off → `FEATURE_DISABLED` |
| Data effects | Reads `beds`, `bed_status_changes` (append-only) |
| Security classification | Configuration (internal) |
| Audit requirement | Status changes as HIMS-FAC-004 |
| Idempotency/concurrency | Read only |
| Integration dependencies | None |
| Acceptance criteria | 1,500 beds load within 500 ms (volume check: 261 ms) |
| Test evidence | `apps/beds/tests/test_bed_board.py`; manual test Part 18g |
| Release risk | Low |

### HIMS-FAC-009

| Field | Record |
|---|---|
| ID and title | HIMS-FAC-009 Equipment register: item, location, status, service dates |
| Business/clinical reason | Hospitals track equipment status and service due dates (spec 4.12); workflows wait for the PO. Owner: PO |
| Actors | `equipment.view`, `equipment.manage` (facility-scoped) |
| Preconditions | Facility; Equipment feature on |
| Main success path | Add items with location; change status with a reason; record service visits with the next due date |
| Alternate/failure paths | Retired items cannot change; missing reason → 400; stale version → 409 |
| Data effects | `equipment`, `equipment_service_records` (append-only visits); status history in the audit log |
| Security classification | Configuration (internal) |
| Audit requirement | `equipment.created`, `equipment.updated`, `equipment.status.changed`, `equipment.service.recorded` |
| Idempotency/concurrency | `version`; history rows never change |
| Integration dependencies | None |
| Acceptance criteria | Overdue service shows; history cannot be edited |
| Test evidence | `apps/equipment/tests/test_equipment.py`; manual test Part 18h |
| Release risk | Low |
