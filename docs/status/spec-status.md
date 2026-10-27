# HIMS — Implementation Status vs Specification v2

Tracks delivery against [HIMS_Architecture_Specification_v2.MD](../../HIMS_Architecture_Specification_v2.MD).
The specification is the source of truth and is **not** edited by this tracker.
Updated after every completed work item.

**Last updated:** 2026-10-28 · **Overall:** ~20% of the full specification · **Phase 1:** ~89%

**Legend**
- ✅ Done: implemented and covered by automated tests
- 🟡 Partial
- ⬜ Not started
- 🔓 Can be built now, with no external dependency
- 🔒 Blocked (the blocker is named)

**Who unblocks what**

| Code | Meaning |
|---|---|
| **PO** | You (product owner): decisions, approvals |
| **CLIN** | Clinical governance: doctors, nurses, pharmacists |
| **LEGAL** | Legal/compliance |
| **AWS** | AWS account and cloud stage (deferred by choice until coding is done) |
| **GH** | GitHub Organization/remote |
| **PAYER** | Stedi, Indian insurers/TPAs |
| **VENDOR** | PACS/LIS/drug-database vendors and licences |

---

## Next work queue: dependency-free, in recommended order

| # | Item | Spec § | Ticket | Status |
|---|---|---|---|---|
| 0 | UI theme selector (white & blue/red/green, minimal black & white) across launcher, apps and admin | 15.2 | HIMS-UI-001 | ✅ (extended to 10 themes in HIMS-UI-002) |
| 1 | Staff invitation and account activation (email to console locally) | 4.4 | HIMS-IAM-003 | ✅ |
| 2 | Password reset (non-enumerating, single-use tokens) | 4.4, 13.1 | HIMS-IAM-004 | ✅ |
| 2b | Hospital roles catalog: designations junior→senior (IN/US), departments/specialties, qualifications, administrative system roles, RBAC document | 3, 4.2, 4.3, 26.4 | HIMS-STAFF-009 | ✅ |
| 2c | Friendly "no access yet" page instead of "Permission denied" for new users (reference number is already recorded in the audit log as `access.denied` → request_id) | 15, 13.4 | HIMS-UI-002 | ✅ Done: welcome page records `access.none_assigned` with its reference; friendlier 403 with reference; 10 themes; compact modern design |
| 3 | End all sessions on suspension/termination (password change already ends them) | 13.5 | HIMS-IAM-006 | ✅ Done: session register; all sessions deleted on deactivation, password change/reset and admin "Sign out of all devices"; audited with count and reason; nightly cleanup |
| 4 | MFA (TOTP) for privileged users and the admin console | 4.4, 13.1 | HIMS-IAM-005 | ✅ Done: authenticator-app codes, required for privileged roles (optional for others), QR setup, 10 backup codes, two-step sign-in in app and admin console, encrypted secret, admin reset for lost phones, ADR-018 |
| 5 | Location hierarchy: building → floor → ward → room → bed (configuration) | 4.1, 4.10 | HIMS-FAC-004 | ✅ Done: buildings, floors, wards/units (12 types incl. ICU/NICU/OT), rooms, beds (13 types); bed status rules (available/maintenance/blocked/out of service by staff; reserved/occupied/cleaning reserved for admissions in Phase 3); bulk bed creation; whole-facility tree with bed counts; new **bed manager** role; Locations page; admin console; [design doc](../architecture/data-architecture/locations-and-beds.md) |
| 5b | Screens to add/edit buildings, floors, wards, rooms and beds in the app | 15.1 | HIMS-FAC-005 | ✅ Done: Locations page now has Add building / floor / ward / room, "Add beds" (numbered, with a preview and a clash warning), Edit and deactivate at every level, bed details from the bed dialog, "Hide inactive"; buttons only for people who may change the layout; codes made safe as you type and locked after creation; server messages shown next to the field. Admin console re-checked for items 1–6 (all models covered, test-enforced) |
| 6 | Hospital numbering schemes (MRN, encounter, invoice, claim) | 4.1 | HIMS-ORG-003 | ✅ Done: hospital-wide and per-facility series; prefix, separator, facility code, restart per calendar/financial year or month, digits; never duplicated, no gaps (GST), facility time zone; India GST 16-character check; "continue from previous system" (forward only); issued-number register; India/US defaults; Numbering page with live preview; admin console; [design doc](../architecture/data-architecture/numbering-schemes.md) |
| 6b | Admin console coverage check (items 1–5) | 13, ADR-016 | HIMS-PLAT-018 | ✅ Done: every model manageable in the admin console (test fails if one is missing); added "Send password reset link" (item 2), bed status Maintenance/Blocked with reason (item 5), Facility → Building → Floor → Ward → Room → Bed drill-down (item 5); location codes locked after creation |
| 7 | Feature flags per organization/country/facility | 4.1 | HIMS-ORG-004 | ✅ Done: Features page (whole hospital or per facility, reason required, audited); 3 live features (forgot-password emails, two-factor for all staff, Locations per facility) enforced by the server; 12 planned modules shown as "Coming in Phase N" and locked; country rules (ABDM/India TPAs India-only, Stedi US-only); admin console lists every feature; [ADR-019](../decisions/ADR-019-feature-flags.md). Admin console re-checked for items 1–7 |
| 8 | Staff UI: detail, onboarding, departments, roles and access | 15 | HIMS-STAFF-007, IAM-013 | 🔓 next |
| 9 | Credential documents (local storage adapter; S3 later) + expiry alerts | 4.3, 4.22 | HIMS-STAFF-005/006 | 🔓 |
| 10 | Audit tamper evidence (hash chain) | 13.4 | HIMS-SEC-010 | 🔓 |
| 11 | Periodic access-review report | 4.4, 13.2 | HIMS-IAM-012 | 🔓 |
| 12 | Artifact A docs for built domains (ERD, data dictionary) | 28 | — | 🔓 |
| 13 | Playwright end-to-end tests for built flows | 19.2 | — | 🔓 |
| 14 | Engineering hygiene: hash-locked lockfile, code splitting, OpenTelemetry (local) | 6.2, 18 | PLAT-012/015/016 | 🔓 |

After this queue, the next big step is **Phase 2 (Patient/MPI)**. It needs a P0 design signed off by
**PO + CLIN** (spec 26). I can draft that design for your approval.

---

## Verification checkpoint: after PR #8 (2026-10-27)

Everything marked ✅ below was re-verified before starting item 5.

| Check | Result |
|---|---|
| Git: local `development` = GitHub `development`, PR #1–#8 merged, working tree clean | ✅ |
| India (`HIMS`) and US (`HIMS_US`) databases: all migrations applied, audit append-only trigger present, 6 system roles, 14 permissions, catalogs (106 designations, 52 specialties, 57 qualification types) | ✅ both |
| Backend: 139 tests, lint/format, Django checks, migrations committed, OpenAPI contract in sync, dependency audit, production `check --deploy` | ✅ |
| Frontend: API types in sync, typecheck, lint, 14 tests, build, dependency audit | ✅ |
| End-to-end regression over HTTP (fresh database, two-factor enforced): 32 checks covering health, problem errors, MFA enforcement/setup/two-step sign-in, facilities + idempotent replay + stale-edit protection, departments, catalogs, staff onboarding + designation, invitation + single-use activation, no-access reference, permission-denied reference, password reset (no enumeration) + sessions ended, role grant, termination ends sessions and blocks sign-in, admin console with code, admin cannot read audit, admin theme, auditor two-factor, auditor finds references, all feature audit events present | ✅ 32/32 |
| Launcher: page, 10 themes, India/US/Europe cards | ✅ |
| Docs: no broken links, 18 ADRs = 18 index rows | ✅ (qualification count corrected 66 → 57; backlog rows added for HIMS-UI-001 and HIMS-OPS-012) |
| Not yet done (by design): `qa`/`staging`/`production` are 8 PRs behind `development` (no promotion yet); hosted environments (Render/Vercel) not created | ℹ️ |

## PR history (traceability, spec 25.3)

| PR | Ticket(s) | What |
|---|---|---|
| #1 | HIMS-OPS-002 | Manual CI runs; GitHub setup recorded |
| #2 | HIMS-OPS-002 (titled "HIMS-OPS-003" by mistake; HIMS-OPS-003 remains *Terraform modules*) | Environment branches renamed to `development`/`production` |
| #3 | HIMS-IAM-003 | Staff invitation and account activation |
| #4 | HIMS-IAM-004, HIMS-STAFF-009 | Password reset; hospital roles catalog; RBAC document |
| #5 | HIMS-UI-002 (extends HIMS-UI-001) | No-access page with audited reference; 10 themes; compact design |
| #6 | HIMS-IAM-006 | End all sessions on suspension/termination/password change |
| #7 | HIMS-OPS-012 | Runbook: updating every hospital database |
| #8 | HIMS-IAM-005 | Two-factor sign-in (MFA); secret-scan exceptions for reviewed false positives |
| #9 | HIMS-OPS-013 | Verification checkpoint after PR #8; PR history; doc corrections |
| #10 | HIMS-FAC-004 | Hospital locations: building → floor → ward → room → bed; bed status rules; bed manager role; Locations page |
| #11 | HIMS-ORG-003, HIMS-PLAT-018 | Numbering schemes (MRN, visit, invoice, claim) with Numbering page; admin console coverage for items 1–5 |
| #12 | HIMS-FAC-005 | Set up locations in the app: add/edit/deactivate buildings, floors, wards, rooms and beds on the Locations page |
| #13 (this item; number assigned by GitHub) | HIMS-ORG-004 | Feature settings per hospital, country and facility; Features page; ADR-019 |
| (before PRs) | HIMS-PLAT-*, HIMS-ORG-*, HIMS-FAC-001..003, HIMS-IAM-001/002/009, HIMS-STAFF-001..004, HIMS-AUD-*, HIMS-PLAT-017, HIMS-UI-001 | Phase 1 foundation, admin console, launcher, themes (direct commits before the PR workflow existed) |

## Section-by-section

### §1 Executive summary · §2 Principles · §3 Personas

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §1 Confirmed direction (stack, monolith, dedicated deployment, IN+US) | ✅ | Followed in code; IN and US deployments run locally | — | — |
| §2.2 Principles 1, 4, 5, 6, 8, 9, 11 | ✅ | State guards, transactions, audit, isolation, modular monolith, PostgreSQL authority, end-to-end security | — | — |
| §2.2 Principles 2, 3, 7, 10, 12 | ⬜ | — | Apply with patient, orders, country adapters, integrations | 🔒 CLIN for 12 |
| §3 Personas (16 roles) | 🟡 7 system roles | Organization admin, auditor, facility admin, HR/credentialing officer, HOD, basic staff, bed manager / ward clerk; all 16 personas documented with ladders in [RBAC doc](Hospital_Departments_and_Doctors_RBAC.MD) | Clinical roles' permissions | 🔒 CLIN (approve RBAC doc §8) |

### §4 Functional scope

| § | Domain | Status | Done | Left (🔓 = can do now) | Dependency |
|---|---|---|---|---|---|
| 4.1 | Hospital & branches | 🟡 90% | Organization (one per deployment), facilities, country/timezone/currency, admin, **locations: buildings, floors, wards/units, rooms, beds** (HIMS-FAC-004), **numbering schemes for MRN, encounters, invoices, claims** (HIMS-ORG-003), **feature flags by organization, country and facility** (HIMS-ORG-004) | 🔓 logo/templates | Tax rules: 🔒 LEGAL |
| 4.2 | Departments | 🟡 40% | Create/edit, facility scope; department catalog & people per department documented; 52 specialties | 🔓 head, services, operating hours | Pricing/slots/escalation: 🔒 CLIN |
| 4.3 | Staff & credentials | 🟡 80% | Staff, qualifications (57 IN/US types), credentials, verification, termination, **designation catalog (106 titles, seniority 1–10, IN/US)** | 🔓 documents, 🔓 expiry alerts, 🔓 shifts/leave/on-call | Clinical privileges: 🔒 CLIN |
| 4.4 | Identity & access | 🟡 88% | Login, sessions, scoped RBAC, suspension, admin console, invitation & activation, password reset (no enumeration, 60 min single-use link, ends all sessions, security notice), **session management** (register of sign-ins per user, end all sessions on suspension/termination/deactivation, "sign out of all devices"), **two-factor sign-in (MFA)** for privileged roles | 🔓 MFA, 🔓 access reviews, 🔓 delegation | SSO: 🔒 PO; break-glass rules: 🔒 CLIN |
| 4.5 | Patient registration & MPI | ⬜ | — | Demographics, MRN, duplicate detection | 🔒 PO+CLIN P0 sign-off |
| 4.6 | Appointments & OPD | ⬜ | — | All | 🔒 P0 |
| 4.7 | Encounters & admissions | ⬜ | — | All | 🔒 P0, CLIN |
| 4.8 | EHR/EMR | ⬜ | — | All | 🔒 CLIN |
| 4.9 | Nursing | ⬜ | — | All | 🔒 CLIN |
| 4.10 | Beds & wards | 🟡 40% | Ward/room/bed inventory with types, gender/age restrictions, isolation-capable rooms; bed status (available, maintenance, blocked, out of service) with reason, audit and `bed.status.changed` event; occupancy counts per ward and facility; Locations page **with in-app setup** (add, edit, deactivate every level; add numbered beds; HIMS-FAC-005) | 🔓 bed board view; assignment, transfer, housekeeping turnaround | Assignment/transfer/discharge: 🔒 P0 ADT (Phase 3) |
| 4.11 | Diet & kitchen | ⬜ | — | All | 🔒 CLIN |
| 4.12 | Housekeeping/equipment/transport | ⬜ | — | 🔓 equipment register | Workflows: 🔒 PO |
| 4.13 | Pharmacy | ⬜ | — | All | 🔒 CLIN, VENDOR (drug database) |
| 4.14 | eMAR | ⬜ | — | All | 🔒 CLIN |
| 4.15 | Laboratory | ⬜ | — | All | 🔒 CLIN, VENDOR (LIS) |
| 4.16 | Radiology | ⬜ | — | All | 🔒 CLIN, VENDOR (PACS) |
| 4.17 | Surgery/ICU | ⬜ | — | All | 🔒 CLIN |
| 4.18 | Insurance | ⬜ | — | All | 🔒 PAYER |
| 4.19 | Billing/RCM | ⬜ | — | All | 🔒 PO+LEGAL (tax), PAYER |
| 4.20 | Procurement/inventory/accounting | ⬜ | — | All | 🔒 PO (finance rules) |
| 4.21 | Patient portal | ⬜ | — | All | 🔒 needs 4.5+ |
| 4.22 | Documents & consent | ⬜ | — | 🔓 document storage service | Consent forms: 🔒 LEGAL |
| 4.23 | Notifications | ⬜ | — | 🔓 notification service (console/email locally) | SMS/WhatsApp: 🔒 VENDOR (DLT) |
| 4.24 | Reporting | ⬜ | — | All | 🔒 needs domains |
| 4.25 | Audit & governance | 🟡 50% | Who/what/when, before/after, logins, denials, admin changes, audit search | 🔓 tamper evidence, 🔓 audit export | Retention/legal hold: 🔒 LEGAL |

### §5 Workflows · §6 Technical architecture · §7 Dedicated deployment · §8 Repository

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §5.1–5.3 Admission, medication, claim flows | ⬜ | — | All | 🔒 §4 domains |
| §6.1 Modular monolith | ✅ | One Django project with domain apps | — | — |
| §6.2 Stack table | 🟡 85% | React/TS, MUI, TanStack, RHF+zod, DRF, PostgreSQL, Celery, Redis (optional locally), OpenAPI, Docker | 🔓 S3-compatible storage adapter, 🔓 OpenTelemetry | — |
| §6.3 Components (outbox, idempotency, audit, tenant context) | ✅ | All present and tested; admin console covers every model (enforced by a test) | Integration gateway | 🔒 PAYER/VENDOR |
| §7.1–7.4 Per-organization deployment and isolation | 🟡 40% | Deployment ID, isolated cookies/cache/queues, single-org database, provisioning command, IN+US running separately | Control plane, export/retirement | 🔒 AWS + PO (account isolation) |
| §7.6 Cross-hospital reporting | ⬜ | — | Governed analytics pipeline | 🔒 LEGAL |
| §8 Repository layout | ✅ | As specified | — | — |

### §9 Data modelling · §10 Concurrency

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §9.2 Organization/Identity/Platform tables | 🟡 | organizations, facilities, departments, users, roles, permissions, role_assignments, staff_*, audit_events, outbox_events, idempotency_records, **buildings, floors, wards, rooms, beds**, **numbering_schemes, numbering_counters, issued_numbers**, **feature_flags** | 🔓 documents | consents: 🔒 LEGAL |
| §9.2 Patient/Clinical/Inpatient/Medication/Lab/Diet/Insurance/Billing tables | ⬜ | — | All | 🔒 P0 per domain |
| §9.4 Doctor & qualification model | ✅ | StaffMember, department assignment, qualification, credential | — | — |
| §10.1 Bed allocation race | 🟡 | Beds exist with row-locked, versioned status changes (stale change → 409); `occupied`/`reserved` can only be set by the future admission workflow | Allocation with partial unique index on active bed assignment | 🔒 P0 ADT |
| §10.2 Duplicate request/claim/payment/Celery protections | 🟡 | Idempotency keys, version checks, deduplicated tasks — all tested; **business numbers (MRN/encounter/invoice/claim) can never be issued twice** (row lock + unique index, 6-thread test) | Domain-specific cases | 🔒 domains |

### §11 Insurance · §12 Interoperability · §13 Security

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §11 Stedi and India adapters, eligibility, claims | ⬜ | — | All | 🔒 PAYER |
| §12 FHIR / ABDM / HIPAA | ⬜ | — | All | 🔒 partners, LEGAL |
| §13.1 Authentication | 🟡 MFA ✅ | Session lifecycle, throttling, no account enumeration, admin lockout, secure activation/reset tokens (signed, single use, never stored, kept out of URLs sent to servers), account recovery, **MFA for privileged users** (TOTP, two-step sign-in in app and admin console, backup codes, replay protection, attempt limits); the hospital can require two-factor for everyone and turn off forgot-password emails on its Features page | 🔓 step-up re-authentication (HIMS-IAM-007), 🔓 passkeys (HIMS-IAM-014) | SSO: 🔒 PO |
| §13.2 Authorization | 🟡 | RBAC + facility/department scope, default deny, separate permissions, escalation guard, **prompt termination of access** (all sessions deleted the moment employment ends) | 🔓 access reviews | Patient/encounter scope & break-glass: 🔒 CLIN |
| §13.3 Data protection | 🟡 | Secrets kept out of git, PHI-minimised logs, **application-level encryption with rotatable keys** (authenticator secrets; production refuses to start without keys) | 🔓 document access controls | TLS/KMS/backups: 🔒 AWS |
| §13.4 Auditability | 🟡 | Append-only (database trigger), restricted access, privileged actions audited; every "no access" / "permission denied" screen shows a reference number equal to the audit event's request ID (searchable by auditors) | 🔓 tamper detection | Retention: 🔒 LEGAL |
| §13.5 Security test cases (10) | 🟡 3/10 | Out-of-scope access, terminated user **reusing an old session (now deleted on every device, tested via API, admin console and direct deactivation)**, Celery context isolation (queues) | 🔓 secret-in-logs test, 🔓 restore test (local) | 7 need domains (notes, stock, documents, exports) |

### §14 Redis/Celery · §15 React · §16 REST API

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §14.2 Transactional outbox | ✅ | Dispatcher, retries, dead-lettering, consumer deduplication, inline mode for local development; first real consumers (invitation emails) | — | — |
| §14.3 Reliability rules | 🟡 | Late acknowledgement, idempotent tasks, durable state | Queue monitoring | 🔒 AWS (alarms); local Redis optional |
| §15.1 Role workspaces | 🟡 1/7 | Hospital-admin workspace (facilities, locations and beds with full in-app setup, numbering, features, staff) | 🔓 more admin screens | Clinical workspaces: 🔒 domains |
| §15.2 Frontend decisions | 🟡 | TypeScript, typed contracts, TanStack, RHF, backend authorization, **theme selector (10 white-based themes, WCAG AA contrast tested)**, compact modern design system (13px base, small sentence-case buttons, dense inputs/tables), permission-aware navigation and home page | 🔓 accessibility checks, 🔓 code splitting | — |
| §15.3 Patient chart | ⬜ | — | All | 🔒 4.5+ |
| §16 Endpoint table (18) | 🟡 4/18 | Hospital setup (provisioning), departments, staff, audit events; plus locations and beds (`/buildings`, `/floors`, `/wards`, `/rooms`, `/beds`, `/beds/{id}/status`, `/beds/bulk`, `/facilities/{id}/locations`) and numbering (`/numbering-schemes`, `/numbering-schemes/preview`, `/numbering-schemes/{id}/next-number`, `/issued-numbers`) and features (`/features`, `/features/{key}/change`, `/features/effective`) | 14 domain endpoints | 🔒 domains |
| §16 Write-endpoint rules (8 items) | ✅ | Applied to all built endpoints | — | — |

### §17 AWS · §18 Non-functional · §19 Testing · §20 Roadmap · §21 Vertical slice

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §17 AWS deployment | ⬜ | Dockerfile ready | All | 🔒 AWS (deferred by choice) |
| §18 Non-functional requirements | 🟡 30% | Consistency, request IDs, structured logs | 🔓 local tracing; SLO measurement | 🔒 AWS |
| §19.1 Backend tests | 🟡 | 205 tests (incl. feature settings: defaults, hospital/facility/country rules, planned features locked, reason + version + audit, the 3 live features enforced, permissions, admin console): constraints, permissions, isolation, concurrency, outbox, admin (incl. every console page opens and every model is in the console), migrations, locations and bed status rules, numbering (formats, periods, no duplicates under 6 parallel threads, no gaps on rollback, GST length) | 🔓 secret-leak and restore tests | Insurance contract tests: 🔒 PAYER |
| §19.2 Frontend tests | 🟡 | 33 tests (incl. Features page, forgot-password link hidden when off, Locations "turned off" message): client, themes, link tokens, home/no-access page, two-factor setup/sign-in/redirect, Locations page and bed status dialog, location setup (view-only hides buttons, add building with field error, edit ward with version + deactivation warning, add numbered beds with clash check, bed details), Numbering page (list, view-only, live preview + save, continue numbering) | 🔓 Playwright end-to-end, 🔓 accessibility | — |
| §19.3 Clinical validation | ⬜ | — | All | 🔒 CLIN |
| §20 Phase 1 | 🟡 89% | See tracker | Queue items 8–14 | — |
| §20 Phases 2–6 | ⬜ | — | All | 🔒 P0/CLIN/PAYER/VENDOR |
| §21 Vertical slice (14 steps) | 🟡 4/14 | Steps 1–4 (hospital, departments, doctor onboarding, scoped access) | Steps 5–14 | 🔒 domains |

### §22 ADRs · §23 Readiness checklist · §24 Links

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §22 ADR-001…008 | ✅ | Recorded in docs/decisions | — | — |
| New ADR-009…019 | 🟡 Proposed | Written and implemented | Approval | 🔒 PO / Security |
| §23 Checklist (45 items) | 🟡 2 done, 6 partial | Migrations version-controlled, outbox tested | 37 items | 🔒 CLIN/LEGAL/AWS/PAYER |
| §24 Reference links | n/a | — | — | — |

### §25–27 Delivery standard, P0, P1

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §25 Requirement IDs & traceability | 🟡 | Ticket IDs in backlog and code | 🔓 formal HIMS-FR records for built features | — |
| P0-A Functional specs | 🟡 | Foundation domains | Clinical domains | 🔒 CLIN |
| P0-B Database design | 🟡 | Built domains (constraints, migrations); [locations and beds design](../architecture/data-architecture/locations-and-beds.md), [numbering design](../architecture/data-architecture/numbering-schemes.md) | 🔓 data dictionary | — |
| P0-C State machines | 🟡 | Employment status, credential verification, **bed status** (operational part; ADT part designed) | Clinical state machines | 🔒 CLIN |
| P0-D Permission matrix | 🟡 | Administrative permissions (21) + 7 system roles (bed manager added; numbering and feature settings for facility administrators); full clinical matrix **drafted** in [RBAC doc §8](Hospital_Departments_and_Doctors_RBAC.MD) | Approval | 🔒 CLIN |
| P0-E Provisioning/isolation | 🟡 | Application side, IN+US locally | Infrastructure side | 🔒 AWS |
| P0-F Integration contracts | ⬜ | — | All | 🔒 PAYER/VENDOR |
| P0-G Regulatory assessment | ⬜ | — | All | 🔒 LEGAL |
| P0-H Terminology | ⬜ | Starter catalogs | Code systems, licences | 🔒 CLIN, VENDOR |
| P0-I API & migration discipline | ✅ | OpenAPI and migration checks in CI | — | — |
| §27 P1 production readiness | ⬜ 5% | Structured logs | DR, runbooks, load tests, UAT | 🔒 AWS, CLIN |

### §28–30 Artifacts A, B, C

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §28 Artifact A — data architecture | 🟡 30% | Schemas via migrations; §28.2 standards followed; domain design documents: locations and beds (tables, constraints, indexes, state machine), numbering schemes (business identifiers separate from keys, uniqueness and concurrency rules) | 🔓 ERD + data dictionary for built domains | — |
| §29 Artifact B — API contracts | 🟡 60% | Baseline, problem errors, idempotency, event envelope, OpenAPI check in CI | 🔓 per-endpoint contract docs; webhooks/adapters | 🔒 PAYER |
| §30 Artifact C — AWS/operations | ⬜ 5% | Dockerfile, infrastructure layout | Terraform, network, KMS, backups | 🔒 AWS |

### §31–36 Environments, GitHub, CI/CD, cost, DoD, decisions

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §31 Environments | 🟡 | Local (IN+US + launcher), startup guard, config rules; feature settings documented as a schema (ADR-019, spec 31.4); environment branches `development`/`qa`/`staging`/`production` created (ADR-017) | Hosted Dev/QA/Staging/Prod on Render + Vercel | 🔒 PO (Render/Vercel accounts) |
| §32 GitHub workflow | 🟡 | Repo `vijayant-pandey/HIMS_Advanced` with branches development→qa→staging→production, ruleset `environment-branches` (PR required, 4 required checks, no force push/deletion), templates, CODEOWNERS template | GitHub Projects board | — |
| §33 CI/CD | 🟡 | PR CI runs on PRs into all four environment branches | Run on GitHub; Render/Vercel auto-deploy per branch | 🔒 GH, PO |
| §34 Cost strategy | 🟡 | Stage A (local, no spend) | Stages B–D | 🔒 AWS |
| §35 Definition of Done | 🟡 | Tests, migrations, contracts, no secrets | Environment/QA evidence | 🔒 AWS |
| §36 Open decisions (19) | ⬜ 0/19 | ADRs propose answers | Decisions | 🔒 PO, LEGAL, CLIN, Finance |

---

## Change log

| Date | Item | Sections affected |
|---|---|---|
| 2026-10-25 | Phase 1 foundation, admin console, IN+US local deployments, launcher | 4.1–4.4, 4.25, 6–10, 13–16, 19, 21, 28–33 |
| 2026-10-26 | UI theme selector (HIMS-UI-001) across launcher, apps and admin | 15.2 |
| 2026-10-26 | Environment branches qa/staging, CI on all four, ADR-017 (Render + Vercel interim hosting) | 31, 32, 33 |
| 2026-10-26 | Code pushed to GitHub, branch ruleset, manual CI trigger (HIMS-OPS-002) | 32, 33 |
| 2026-10-26 | Environment branches renamed to development/production; CI, README, ADR-017 updated | 31, 32, 33 |
| 2026-10-26 | Staff invitation & account activation (HIMS-IAM-003): email link, activation page, resend from API/admin, outbox inline mode locally | 4.4, 13.1, 14.2, 19 |
| 2026-10-26 | Password reset (HIMS-IAM-004); hospital roles catalog + RBAC document (HIMS-STAFF-009); HIMS-UI-002 tracked | 3, 4.2, 4.3, 4.4, 13.1, 26.4 |
| 2026-10-26 | HIMS-UI-002: no-access welcome page (audited reference), friendlier 403, 10 themes, compact modern design | 13.4, 15.2 |
| 2026-10-26 | HIMS-IAM-006: end all sessions on suspension/termination/deactivation, password change and admin sign-out; session register; nightly expired-session cleanup | 4.4, 13.2, 13.5, 14 |
| 2026-10-26 | Runbook: updating every hospital database after a merge (docs/workflows/database-migrations.md) | 26.9, 28.7, 31 |
| 2026-10-26 | HIMS-IAM-005: two-factor sign-in (MFA) for privileged roles, Security page, admin-console code step, encrypted secrets, ADR-018 | 4.4, 13.1, 13.3, 13.4 |
| 2026-10-27 | Verification checkpoint after PR #8 (all gates + 32-step end-to-end regression); docs corrected (qualification count, backlog rows, PR history) | 25.3 |
| 2026-10-27 | HIMS-FAC-004: locations (building → floor → ward → room → bed), bed status rules, bed manager role, Locations page, design doc; HIMS-FAC-005 (in-app setup screens) added to the queue | 3, 4.1, 4.10, 9.2, 10.1, 15.1, 16, 19, 26 (P0-B/C/D), 28 |
| 2026-10-27 | HIMS-ORG-003: numbering schemes (MRN, encounter, invoice, claim) with Numbering page, preview, continue-from-previous-system, issued register, India/US defaults, design doc. HIMS-PLAT-018: admin console covers every model (test-enforced), password-reset action, full bed status and location drill-down in the console | 4.1, 6.3, 9.2, 10.2, 15.1, 16, 19, 26 (P0-B/D), 28 |
| 2026-10-28 | HIMS-FAC-005: set up locations in the app (add/edit/deactivate buildings, floors, wards, rooms; add numbered beds; bed details); location tree now carries versions and department names; admin console re-checked for items 1–6 | 4.10, 15.1, 19 |
| 2026-10-28 | HIMS-ORG-004: feature settings by organization, country and facility (Features page, 3 live features, 12 planned modules, admin console, ADR-019); admin console re-checked for items 1–7 | 4.1, 7.2, 13.1, 15.1, 16, 19, 22, 26 (P0-D), 31.4 |
