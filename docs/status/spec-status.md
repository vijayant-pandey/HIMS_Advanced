# HIMS — Implementation Status vs Specification v2

Tracks delivery against [HIMS_Architecture_Specification_v2.MD](../../HIMS_Architecture_Specification_v2.MD).
The specification is the source of truth and is **not** edited by this tracker.
Updated after every completed work item.

**Last updated:** 2026-10-26 · **Overall:** ~15% of the full specification · **Phase 1:** ~66%

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
| 0 | UI theme selector (white & blue/red/green, minimal black & white) across launcher, apps and admin | 15.2 | HIMS-UI-001 | ✅ |
| 1 | Staff invitation and account activation (email to console locally) | 4.4 | HIMS-IAM-003 | ✅ |
| 2 | Password reset (non-enumerating, single-use tokens) | 4.4, 13.1 | HIMS-IAM-004 | ✅ |
| 2b | Hospital roles catalog: designations junior→senior (IN/US), departments/specialties, qualifications, administrative system roles, RBAC document | 3, 4.2, 4.3, 26.4 | HIMS-STAFF-009 | ✅ |
| 2c | Friendly "no access yet" page instead of "Permission denied" for new users (reference number is already recorded in the audit log as `access.denied` → request_id) | 15, 13.4 | HIMS-UI-002 | 🔓 tracked — product owner will schedule |
| 3 | End all sessions on suspension/termination (password change already ends them) | 13.5 | HIMS-IAM-006 | 🔓 next |
| 4 | MFA (TOTP) for privileged users and the admin console | 4.4, 13.1 | HIMS-IAM-005 | 🔓 |
| 5 | Location hierarchy: building → floor → ward → room → bed (configuration) | 4.1, 4.10 | HIMS-FAC-004 | 🔓 |
| 6 | Hospital numbering schemes (MRN, encounter, invoice, claim) | 4.1 | HIMS-ORG-003 | 🔓 |
| 7 | Feature flags per organization/country/facility | 4.1 | HIMS-ORG-004 | 🔓 |
| 8 | Staff UI: detail, onboarding, departments, roles and access | 15 | HIMS-STAFF-007, IAM-013 | 🔓 |
| 9 | Credential documents (local storage adapter; S3 later) + expiry alerts | 4.3, 4.22 | HIMS-STAFF-005/006 | 🔓 |
| 10 | Audit tamper evidence (hash chain) | 13.4 | HIMS-SEC-010 | 🔓 |
| 11 | Periodic access-review report | 4.4, 13.2 | HIMS-IAM-012 | 🔓 |
| 12 | Artifact A docs for built domains (ERD, data dictionary) | 28 | — | 🔓 |
| 13 | Playwright end-to-end tests for built flows | 19.2 | — | 🔓 |
| 14 | Engineering hygiene: hash-locked lockfile, code splitting, OpenTelemetry (local) | 6.2, 18 | PLAT-012/015/016 | 🔓 |

After this queue, the next big step is **Phase 2 (Patient/MPI)**. It needs a P0 design signed off by
**PO + CLIN** (spec 26). I can draft that design for your approval.

---

## Section-by-section

### §1 Executive summary · §2 Principles · §3 Personas

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §1 Confirmed direction (stack, monolith, dedicated deployment, IN+US) | ✅ | Followed in code; IN and US deployments run locally | — | — |
| §2.2 Principles 1, 4, 5, 6, 8, 9, 11 | ✅ | State guards, transactions, audit, isolation, modular monolith, PostgreSQL authority, end-to-end security | — | — |
| §2.2 Principles 2, 3, 7, 10, 12 | ⬜ | — | Apply with patient, orders, country adapters, integrations | 🔒 CLIN for 12 |
| §3 Personas (16 roles) | 🟡 6 system roles | Organization admin, auditor, facility admin, HR/credentialing officer, HOD, basic staff; all 16 personas documented with ladders in [RBAC doc](Hospital_Departments_and_Doctors_RBAC.MD) | Clinical roles' permissions | 🔒 CLIN (approve RBAC doc §8) |

### §4 Functional scope

| § | Domain | Status | Done | Left (🔓 = can do now) | Dependency |
|---|---|---|---|---|---|
| 4.1 | Hospital & branches | 🟡 50% | Organization (one per deployment), facilities, country/timezone/currency, admin | 🔓 numbering schemes, 🔓 wards/rooms/beds, 🔓 feature flags, 🔓 logo/templates | Tax rules: 🔒 LEGAL |
| 4.2 | Departments | 🟡 40% | Create/edit, facility scope; department catalog & people per department documented; 52 specialties | 🔓 head, services, operating hours | Pricing/slots/escalation: 🔒 CLIN |
| 4.3 | Staff & credentials | 🟡 80% | Staff, qualifications (66 IN/US types), credentials, verification, termination, **designation catalog (106 titles, seniority 1–10, IN/US)** | 🔓 documents, 🔓 expiry alerts, 🔓 shifts/leave/on-call | Clinical privileges: 🔒 CLIN |
| 4.4 | Identity & access | 🟡 70% | Login, sessions, scoped RBAC, suspension, admin console, invitation & activation, **password reset** (no enumeration, 60 min single-use link, ends all sessions, security notice) | 🔓 MFA, 🔓 access reviews, 🔓 delegation | SSO: 🔒 PO; break-glass rules: 🔒 CLIN |
| 4.5 | Patient registration & MPI | ⬜ | — | Demographics, MRN, duplicate detection | 🔒 PO+CLIN P0 sign-off |
| 4.6 | Appointments & OPD | ⬜ | — | All | 🔒 P0 |
| 4.7 | Encounters & admissions | ⬜ | — | All | 🔒 P0, CLIN |
| 4.8 | EHR/EMR | ⬜ | — | All | 🔒 CLIN |
| 4.9 | Nursing | ⬜ | — | All | 🔒 CLIN |
| 4.10 | Beds & wards | ⬜ | — | 🔓 bed inventory/configuration (queue #5); assignment workflow | Assignment: 🔒 P0 |
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
| §6.3 Components (outbox, idempotency, audit, tenant context) | ✅ | All present and tested | Integration gateway | 🔒 PAYER/VENDOR |
| §7.1–7.4 Per-organization deployment and isolation | 🟡 40% | Deployment ID, isolated cookies/cache/queues, single-org database, provisioning command, IN+US running separately | Control plane, export/retirement | 🔒 AWS + PO (account isolation) |
| §7.6 Cross-hospital reporting | ⬜ | — | Governed analytics pipeline | 🔒 LEGAL |
| §8 Repository layout | ✅ | As specified | — | — |

### §9 Data modelling · §10 Concurrency

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §9.2 Organization/Identity/Platform tables | 🟡 | organizations, facilities, departments, users, roles, permissions, role_assignments, staff_*, audit_events, outbox_events, idempotency_records | 🔓 wards/rooms/beds, 🔓 documents | consents: 🔒 LEGAL |
| §9.2 Patient/Clinical/Inpatient/Medication/Lab/Diet/Insurance/Billing tables | ⬜ | — | All | 🔒 P0 per domain |
| §9.4 Doctor & qualification model | ✅ | StaffMember, department assignment, qualification, credential | — | — |
| §10.1 Bed allocation race | ⬜ | Pattern ready (row locks, partial unique index) | Implement with beds | 🔒 P0 ADT |
| §10.2 Duplicate request/claim/payment/Celery protections | 🟡 | Idempotency keys, version checks, deduplicated tasks — all tested | Domain-specific cases | 🔒 domains |

### §11 Insurance · §12 Interoperability · §13 Security

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §11 Stedi and India adapters, eligibility, claims | ⬜ | — | All | 🔒 PAYER |
| §12 FHIR / ABDM / HIPAA | ⬜ | — | All | 🔒 partners, LEGAL |
| §13.1 Authentication | 🟡 | Session lifecycle, throttling, no account enumeration, admin lockout, secure activation/reset tokens (signed, single use, never stored, kept out of URLs sent to servers), account recovery | 🔓 MFA, 🔓 reauthentication | — |
| §13.2 Authorization | 🟡 | RBAC + facility/department scope, default deny, separate permissions, escalation guard | 🔓 access reviews | Patient/encounter scope & break-glass: 🔒 CLIN |
| §13.3 Data protection | 🟡 | Secrets kept out of git, PHI-minimised logs | 🔓 document access controls | TLS/KMS/backups: 🔒 AWS |
| §13.4 Auditability | 🟡 | Append-only (database trigger), restricted access, privileged actions audited | 🔓 tamper detection | Retention: 🔒 LEGAL |
| §13.5 Security test cases (10) | 🟡 3/10 | Out-of-scope access, terminated user, Celery context isolation (queues) | 🔓 secret-in-logs test, 🔓 restore test (local) | 7 need domains (notes, stock, documents, exports) |

### §14 Redis/Celery · §15 React · §16 REST API

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §14.2 Transactional outbox | ✅ | Dispatcher, retries, dead-lettering, consumer deduplication, inline mode for local development; first real consumers (invitation emails) | — | — |
| §14.3 Reliability rules | 🟡 | Late acknowledgement, idempotent tasks, durable state | Queue monitoring | 🔒 AWS (alarms); local Redis optional |
| §15.1 Role workspaces | 🟡 1/7 | Hospital-admin workspace (facilities, staff) | 🔓 more admin screens | Clinical workspaces: 🔒 domains |
| §15.2 Frontend decisions | 🟡 | TypeScript, typed contracts, TanStack, RHF, backend authorization, **theme selector** | 🔓 accessibility checks, 🔓 code splitting | — |
| §15.3 Patient chart | ⬜ | — | All | 🔒 4.5+ |
| §16 Endpoint table (18) | 🟡 4/18 | Hospital setup (provisioning), departments, staff, audit events | 14 domain endpoints | 🔒 domains |
| §16 Write-endpoint rules (8 items) | ✅ | Applied to all built endpoints | — | — |

### §17 AWS · §18 Non-functional · §19 Testing · §20 Roadmap · §21 Vertical slice

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §17 AWS deployment | ⬜ | Dockerfile ready | All | 🔒 AWS (deferred by choice) |
| §18 Non-functional requirements | 🟡 30% | Consistency, request IDs, structured logs | 🔓 local tracing; SLO measurement | 🔒 AWS |
| §19.1 Backend tests | 🟡 | 101 tests: constraints, permissions, isolation, concurrency, outbox, admin, migrations | 🔓 secret-leak and restore tests | Insurance contract tests: 🔒 PAYER |
| §19.2 Frontend tests | 🟡 | Unit tests for client, themes and link-token handling | 🔓 Playwright end-to-end, 🔓 accessibility | — |
| §19.3 Clinical validation | ⬜ | — | All | 🔒 CLIN |
| §20 Phase 1 | 🟡 66% | See tracker | Queue items 1–14 | — |
| §20 Phases 2–6 | ⬜ | — | All | 🔒 P0/CLIN/PAYER/VENDOR |
| §21 Vertical slice (14 steps) | 🟡 4/14 | Steps 1–4 (hospital, departments, doctor onboarding, scoped access) | Steps 5–14 | 🔒 domains |

### §22 ADRs · §23 Readiness checklist · §24 Links

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §22 ADR-001…008 | ✅ | Recorded in docs/decisions | — | — |
| New ADR-009…016 | 🟡 Proposed | Written and implemented | Approval | 🔒 PO / Security |
| §23 Checklist (45 items) | 🟡 2 done, 6 partial | Migrations version-controlled, outbox tested | 37 items | 🔒 CLIN/LEGAL/AWS/PAYER |
| §24 Reference links | n/a | — | — | — |

### §25–27 Delivery standard, P0, P1

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §25 Requirement IDs & traceability | 🟡 | Ticket IDs in backlog and code | 🔓 formal HIMS-FR records for built features | — |
| P0-A Functional specs | 🟡 | Foundation domains | Clinical domains | 🔒 CLIN |
| P0-B Database design | 🟡 | Built domains (constraints, migrations) | 🔓 data dictionary | — |
| P0-C State machines | 🟡 | Employment status, credential verification | Clinical state machines | 🔒 CLIN |
| P0-D Permission matrix | 🟡 | Administrative permissions + 6 system roles; full clinical matrix **drafted** in [RBAC doc §8](Hospital_Departments_and_Doctors_RBAC.MD) | Approval | 🔒 CLIN |
| P0-E Provisioning/isolation | 🟡 | Application side, IN+US locally | Infrastructure side | 🔒 AWS |
| P0-F Integration contracts | ⬜ | — | All | 🔒 PAYER/VENDOR |
| P0-G Regulatory assessment | ⬜ | — | All | 🔒 LEGAL |
| P0-H Terminology | ⬜ | Starter catalogs | Code systems, licences | 🔒 CLIN, VENDOR |
| P0-I API & migration discipline | ✅ | OpenAPI and migration checks in CI | — | — |
| §27 P1 production readiness | ⬜ 5% | Structured logs | DR, runbooks, load tests, UAT | 🔒 AWS, CLIN |

### §28–30 Artifacts A, B, C

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §28 Artifact A — data architecture | 🟡 20% | Schemas via migrations; §28.2 standards followed | 🔓 ERD + data dictionary for built domains | — |
| §29 Artifact B — API contracts | 🟡 60% | Baseline, problem errors, idempotency, event envelope, OpenAPI check in CI | 🔓 per-endpoint contract docs; webhooks/adapters | 🔒 PAYER |
| §30 Artifact C — AWS/operations | ⬜ 5% | Dockerfile, infrastructure layout | Terraform, network, KMS, backups | 🔒 AWS |

### §31–36 Environments, GitHub, CI/CD, cost, DoD, decisions

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §31 Environments | 🟡 | Local (IN+US + launcher), startup guard, config rules; environment branches `development`/`qa`/`staging`/`production` created (ADR-017) | Hosted Dev/QA/Staging/Prod on Render + Vercel | 🔒 PO (Render/Vercel accounts) |
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
