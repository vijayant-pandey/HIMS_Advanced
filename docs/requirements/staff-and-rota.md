# Requirement records: staff, credentials, rota and leave

Spec sections 4.3, 9.4. Format: [README](README.md). Endpoints:
[staff](../architecture/api-and-integrations/endpoints/staff.md),
[rota, leave and staffing](../architecture/api-and-integrations/endpoints/rosters.md).

### HIMS-STAFF-001

| Field | Record |
|---|---|
| ID and title | HIMS-STAFF-001 Staff members, department postings, qualifications and credentials (spec 9.4) |
| Business/clinical reason | The hospital must know who works where and with which registrations before anyone treats patients. Owner: PO; credential rules CLIN |
| Actors | `staff.view` (department-scoped), `staff.manage` |
| Preconditions | Facilities and departments |
| Main success path | Add a person with designation and employment details; post them to departments; add qualifications and licences |
| Alternate/failure paths | Duplicate employee number → 409; posting to an inactive department → 409; ending a posting keeps history |
| Data effects | `staff_members`, `staff_department_assignments`, `staff_qualifications`, `staff_credentials`, `users`; outbox `staff.member.created` |
| Security classification | Staff personal data (confidential) |
| Audit requirement | `staff.member.created`, `staff.member.updated`, `staff.department.assigned`, `staff.department.assignment_ended`, `staff.qualification.added`, `staff.credential.added` |
| Idempotency/concurrency | Idempotency-Key on creates; `version` on changes |
| Integration dependencies | Email for the invitation (through the outbox) |
| Acceptance criteria | A new person gets an invitation once; history of postings is never lost |
| Test evidence | `apps/staff/tests/test_staff_onboarding.py`; browser test `03-staff-and-access.spec.ts`; manual test Part 8 |
| Release risk | Privacy (staff data). Rollback: changes are edits, audited |

### HIMS-STAFF-002

| Field | Record |
|---|---|
| ID and title | HIMS-STAFF-002 Controlled specialty and qualification catalogs (starter set) |
| Business/clinical reason | Free text would make specialties unsearchable and unreportable. Owner: clinical informatics (CLIN) |
| Actors | `staff.view` (read), `catalogs.manage` (change) |
| Preconditions | Seeded catalogs |
| Main success path | Choose from the lists; administrators add or switch off entries |
| Alternate/failure paths | Duplicate code → 409; switched-off entries stay on old records but leave the drop-downs |
| Data effects | `specialties`, `qualification_types` |
| Security classification | Configuration (internal) |
| Audit requirement | `staff.catalog.created`, `staff.catalog.updated` |
| Idempotency/concurrency | `version` on changes |
| Integration dependencies | None |
| Acceptance criteria | Entries are never deleted |
| Test evidence | `apps/staff/tests/test_designations_and_roles.py`; manual test Part 7 |
| Release risk | Low |

### HIMS-STAFF-003

| Field | Record |
|---|---|
| ID and title | HIMS-STAFF-003 Credential verification with separation of duties |
| Business/clinical reason | A licence must be checked by someone other than the holder or the person who entered it. Owner: CLIN |
| Actors | `staff.credentials.verify` (HR/credentialing officer) |
| Preconditions | A credential or qualification added |
| Main success path | Verify or reject against the issuer, with a note |
| Alternate/failure paths | Verifying your own → 403; already decided → 409 |
| Data effects | `staff_credentials`, `staff_qualifications` |
| Security classification | Staff personal data (confidential) |
| Audit requirement | `staff.credential.verified`, `staff.qualification.verified` |
| Idempotency/concurrency | Row lock and state check |
| Integration dependencies | None (checks against registries are manual for now) |
| Acceptance criteria | Nobody verifies their own licence |
| Test evidence | `apps/staff/tests/test_staff_onboarding.py`; manual test Part 8 |
| Release risk | Clinical if unchecked licences looked verified (state shown explicitly) |

### HIMS-STAFF-004

| Field | Record |
|---|---|
| ID and title | HIMS-STAFF-004 Termination and suspension switch off sign-in |
| Business/clinical reason | Leavers lose access the moment they leave (spec 13.5). Owner: PO |
| Actors | `staff.manage` |
| Preconditions | Staff member with an account |
| Main success path | Set status to suspended or terminated; the account is switched off and every session ends |
| Alternate/failure paths | Reactivating a suspended person switches sign-in back on; terminated stays off |
| Data effects | `staff_members`, `users`, `user_sessions` |
| Security classification | Staff personal data (confidential) |
| Audit requirement | `staff.member.updated`, `user.account.deactivated`, `auth.sessions.ended` |
| Idempotency/concurrency | `version` |
| Integration dependencies | None |
| Acceptance criteria | The next request of a terminated person is refused |
| Test evidence | `apps/staff/tests/test_staff_onboarding.py`, `apps/identity/tests/test_sessions.py`; manual test Part 19 |
| Release risk | Privacy if broken |

### HIMS-STAFF-005

| Field | Record |
|---|---|
| ID and title | HIMS-STAFF-005 Licence and qualification documents: upload with type and size checks; audited downloads (ADR-020) |
| Business/clinical reason | Proof of registration is kept with the record. Owner: PO |
| Actors | `staff.manage` (upload, archive), `staff.documents.view` (open) |
| Preconditions | A credential or qualification; virus scanner reachable |
| Main success path | Upload a PDF, JPEG or PNG; it is scanned, stored with its checksum and listed; every download audited |
| Alternate/failure paths | Wrong type or too big → 400; virus → refused, audited and the compliance team told; scanner down → `SCANNER_UNAVAILABLE`; wrong files are archived with a reason, never deleted |
| Data effects | `staff_documents`; file storage |
| Security classification | Staff personal data (confidential) |
| Audit requirement | `staff.document.uploaded`, `staff.document.downloaded`, `staff.document.archived`, `upload.blocked` |
| Idempotency/concurrency | Each upload is a new document |
| Integration dependencies | Virus scanner (HIMS-SEC-013); storage (S3-compatible at hosting, HIMS-OPS-015) |
| Acceptance criteria | No download without `staff.documents.view`; every download in the audit log |
| Test evidence | `apps/staff/tests/test_documents_and_expiry.py`, `common/tests/test_virus_scan.py`; manual test Part 8 |
| Release risk | Privacy. Rollback: archive |

### HIMS-STAFF-006

| Field | Record |
|---|---|
| ID and title | HIMS-STAFF-006 Credential expiry alerts (daily job and messages) and the Licence expiry page |
| Business/clinical reason | Nobody should practise on an expired licence. Owner: CLIN |
| Actors | Daily job; `staff.view` for the page |
| Preconditions | Credentials with expiry dates |
| Main success path | Each day, licences expiring within 60, 30 and 7 days (`HIMS_CREDENTIAL_ALERT_DAYS`) send one message per threshold to the HR team; the page lists them |
| Alternate/failure paths | An alert already sent for that threshold is not repeated; email failures retry |
| Data effects | `staff_credential_expiry_alerts`, `notifications` |
| Security classification | Staff personal data (confidential) |
| Audit requirement | `staff.credential.expiry_alert_sent` |
| Idempotency/concurrency | Unique rule per credential and threshold |
| Integration dependencies | Email |
| Acceptance criteria | "Today" is the hospital's day (HIMS-STAFF-011) |
| Test evidence | `apps/staff/tests/test_documents_and_expiry.py`; manual test Part 13 |
| Release risk | Clinical if alerts stopped (Background jobs page shows the job) |

### HIMS-STAFF-007

| Field | Record |
|---|---|
| ID and title | HIMS-STAFF-007 Staff detail and onboarding screens |
| Business/clinical reason | HR staff onboard people without a developer. Owner: PO |
| Actors | `staff.view`, `staff.manage` |
| Preconditions | HIMS-STAFF-001 |
| Main success path | Staff page: add, open, edit; tabs for postings, qualifications, licences, documents, access, privileges |
| Alternate/failure paths | Validation errors per field; read-only users see no buttons |
| Data effects | As HIMS-STAFF-001 |
| Security classification | Staff personal data (confidential) |
| Audit requirement | As HIMS-STAFF-001 |
| Idempotency/concurrency | As HIMS-STAFF-001 |
| Integration dependencies | Email |
| Acceptance criteria | Everything an administrator can do in the console can be done on the page |
| Test evidence | `apps/staff/tests/test_staff_screens.py`; browser test `03-staff-and-access.spec.ts`; manual test Part 8 |
| Release risk | Low |

### HIMS-STAFF-008

| Field | Record |
|---|---|
| ID and title | HIMS-STAFF-008 Staff directory limited to your own departments; documents need their own permission |
| Business/clinical reason | A head of department needs their own team, not the whole hospital's personal data. Owner: PO |
| Actors | `staff.view` at department scope; `staff.documents.view` |
| Preconditions | Department grants |
| Main success path | The directory shows people posted to departments in the caller's scope |
| Alternate/failure paths | Someone outside your departments → 404 |
| Data effects | Reads only |
| Security classification | Staff personal data (confidential) |
| Audit requirement | Refusals `access.denied`; downloads as HIMS-STAFF-005 |
| Idempotency/concurrency | Read only |
| Integration dependencies | None |
| Acceptance criteria | A department grant never lists another department's staff |
| Test evidence | `apps/staff/tests/test_directory_scope.py`; manual test Part 11 |
| Release risk | Privacy |

### HIMS-STAFF-009

| Field | Record |
|---|---|
| ID and title | HIMS-STAFF-009 Designation catalog (India and US, junior to senior) and extended catalogs |
| Business/clinical reason | Job titles differ by country; reports need a fixed list. Owner: PO; RBAC document approved for now 2026-11-08 |
| Actors | `staff.view`, `catalogs.manage` |
| Preconditions | Organization country |
| Main success path | The country's designations are seeded; administrators add their own |
| Alternate/failure paths | Duplicate code → 409 |
| Data effects | `designations` |
| Security classification | Configuration (internal) |
| Audit requirement | `staff.catalog.created`, `staff.catalog.updated` |
| Idempotency/concurrency | `version` |
| Integration dependencies | None |
| Acceptance criteria | A US hospital sees US titles, an Indian hospital Indian ones |
| Test evidence | `apps/staff/tests/test_designations_and_roles.py`; manual test Part 7 |
| Release risk | Low |

### HIMS-STAFF-010

| Field | Record |
|---|---|
| ID and title | HIMS-STAFF-010 Catalog screens: designations, specialties, qualification types |
| Business/clinical reason | Catalogs are kept by the hospital. Owner: PO |
| Actors | `staff.view`, `catalogs.manage` |
| Preconditions | HIMS-STAFF-002, -009 |
| Main success path | Job titles and catalogs page: add, edit, switch off |
| Alternate/failure paths | Switched-off entries can be switched back on |
| Data effects | `designations`, `specialties`, `qualification_types` |
| Security classification | Configuration (internal) |
| Audit requirement | `staff.catalog.created`, `staff.catalog.updated` |
| Idempotency/concurrency | `version` |
| Integration dependencies | None |
| Acceptance criteria | Nothing is deleted |
| Test evidence | `apps/staff/tests/test_designations_and_roles.py`; manual test Part 7 |
| Release risk | Low |

### HIMS-STAFF-011

| Field | Record |
|---|---|
| ID and title | HIMS-STAFF-011 "Today" is the hospital's day, not UTC's |
| Business/clinical reason | A licence that expired yesterday in India showed as valid until 05:30. Owner: PO |
| Actors | Every date rule (expiry, postings, reviews, audit day search, rota) |
| Preconditions | Organization time zone |
| Main success path | All date decisions use the hospital's time zone (`apps.organizations.dates`) |
| Alternate/failure paths | Code using the server clock fails a guard test |
| Data effects | None |
| Security classification | Not applicable (behaviour) |
| Audit requirement | None of its own |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | None |
| Acceptance criteria | No app code calls the server's local date (test) |
| Test evidence | `apps/organizations/tests/test_hospital_dates.py` |
| Release risk | Clinical if dates were off by one (guarded) |

### HIMS-STAFF-012

| Field | Record |
|---|---|
| ID and title | HIMS-STAFF-012 Shifts, on-call and leave: Rota, Leave and My schedule pages |
| Business/clinical reason | Departments plan who works when; nobody is double-booked or rostered on leave (spec 4.3). Owner: PO |
| Actors | `rota.view`, `rota.manage` (department), `leave.approve`; every person for their own schedule and leave |
| Preconditions | Departments, staff postings, shift types |
| Main success path | Plan shifts for a week, copy a week, cancel with a reason; ask for leave, approve or reject |
| Alternate/failure paths | Overlapping shifts refused by the database; deciding your own leave → refused; already decided → `ALREADY_DECIDED`; stale version → 409 |
| Data effects | `shift_types`, `shifts`, `leave_requests` |
| Security classification | Staff personal data (confidential) |
| Audit requirement | `rota.shift_type.created`, `rota.shift_type.updated`, `rota.shift.added`, `rota.shift.cancelled`, `leave.requested`, `leave.approved`, `leave.rejected`, `leave.cancelled` |
| Idempotency/concurrency | Exclusion constraint against double booking; `version` on leave; Idempotency-Key on creates |
| Integration dependencies | Email on decisions |
| Acceptance criteria | Two planners booking one person at once: one is refused |
| Test evidence | `apps/rosters/tests/test_rosters.py`; manual test Part 18a |
| Release risk | Operational (staffing). Rollback: cancel shifts |

### HIMS-STAFF-013

| Field | Record |
|---|---|
| ID and title | HIMS-STAFF-013 Leave balances and entitlements (days per year, carry-over) |
| Business/clinical reason | People and approvers see how much leave is left. Owner: PO |
| Actors | `leave.policy.manage` (entitlements, adjustments); `leave.approve`; every person sees their own |
| Preconditions | HIMS-STAFF-012 |
| Main success path | Set days per year per leave type; balances = entitlement + carry-over + adjustments − approved leave |
| Alternate/failure paths | Approving beyond the balance is refused (`LEAVE_OVER_BALANCE`) unless the approver allows it with a note; adjustments need a reason |
| Data effects | `leave_entitlements`, `leave_balance_adjustments` (append-only) |
| Security classification | Staff personal data (confidential) |
| Audit requirement | `leave.entitlement.created`, `leave.entitlement.updated`, `leave.balance.adjusted` |
| Idempotency/concurrency | `version`; adjustments never change |
| Integration dependencies | None |
| Acceptance criteria | The balance always equals the sum of its parts |
| Test evidence | `apps/rosters/tests/test_leave_balances.py`; manual test Part 18m |
| Release risk | Low |

### HIMS-STAFF-015

| Field | Record |
|---|---|
| ID and title | HIMS-STAFF-015 Minimum staffing per shift, with alerts for gaps |
| Business/clinical reason | Wards must not run below safe numbers; planners need warning (spec 4.3, 4.23). Owner: CLIN for the numbers |
| Actors | `rota.manage`; daily job |
| Preconditions | Shift types and requirements |
| Main success path | Set the fewest people per shift; the Rota page warns; one email per gap in the next 7 days |
| Alternate/failure paths | Planning is never blocked; one alert per gap |
| Data effects | `staffing_requirements`, `staffing_gap_alerts`, `notifications` |
| Security classification | Configuration (internal) |
| Audit requirement | `rota.staffing_requirement.created`, `rota.staffing_requirement.updated`, `rota.staffing_gap_alert.sent` |
| Idempotency/concurrency | Unique alert per gap |
| Integration dependencies | Email |
| Acceptance criteria | A gap is warned once, not daily |
| Test evidence | `apps/rosters/tests/test_minimum_staffing.py`; manual test Part 18l |
| Release risk | Clinical if alerts stopped (job on Background jobs) |

### HIMS-STAFF-016

| Field | Record |
|---|---|
| ID and title | HIMS-STAFF-016 Clinical privileges: what each doctor may perform |
| Business/clinical reason | Hospitals grant privileges per procedure; Phase 4 orders will check them. Owner: CLIN |
| Actors | `staff.privileges.manage`; `staff.view` to read |
| Preconditions | Privilege catalog; staff member |
| Main success path | Grant a privilege with dates; end it with a reason |
| Alternate/failure paths | Nobody grants one to themselves; overlapping active grant → 409 |
| Data effects | `clinical_privileges`, `staff_privileges` |
| Security classification | Staff personal data (confidential) |
| Audit requirement | `staff.privilege.granted`, `staff.privilege.ended`, `staff.catalog.created` |
| Idempotency/concurrency | Unique active grant; row lock on end |
| Integration dependencies | None |
| Acceptance criteria | Ended privileges stay on record |
| Test evidence | `apps/staff/tests/test_clinical_privileges.py`; manual test Part 18k |
| Release risk | Clinical later (orders). Rollback: end the privilege |
