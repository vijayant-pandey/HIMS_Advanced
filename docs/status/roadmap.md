# HIMS roadmap: what is done, what is left, and in what order

Built from [HIMS_Architecture_Specification_v2.MD](../../HIMS_Architecture_Specification_v2.MD)
section 20 (phases), 4 (domains), 21 (vertical slice), 26–27 (P0/P1), 36 (decisions), and from the
[tracker](spec-status.md) and backlogs ([Phase 1](../backlog/phase-1-foundation.md),
[Phase 2](../backlog/phase-2-patients.md)). The tracker stays the detailed record; this page is the
ordered plan. **Last updated:** 2026-11-08 (after PR #37, with HIMS-OPS-009 built).

**Legend:** ✅ done · 🟡 partly done · ⬜ not started · 🔓 can be built now · 🔒 blocked (blocker
named) · **PO** you · **CLIN** doctors/nurses/pharmacists · **LEGAL** legal/compliance · **AWS**
cloud stage (deferred by your choice) · **PAYER** Stedi, Indian insurers/TPAs · **VENDOR**
PACS/LIS/drug database/SMS.

## 1. Summary

| Measure | Count |
|---|---|
| Phases in the spec (section 20) | 6 |
| Phases finished | 0 (Phase 1 application part nearly finished; its cloud part deferred) |
| Phases in progress | 1 (Phase 1) |
| Phases not started | 5 (Phase 2 design drafted, waiting for sign-off) |
| Spec sections (1–36) | 36: ✅ 2 · 🟡 26 · ⬜ 7 · not applicable 1 (section 24, links) |
| Functional domains (section 4.1–4.25) | 25: 🟡 8 started · ⬜ 17 not started |
| Phase 1 tickets | 117: ✅ 77 done or drafted · 40 left: 19 🔓 can be built now (4 of them optional or later), 21 🔒 blocked (4 of those move with Phase 2) |
| Phase 2 tickets (already written) | 20: all ⬜, all 🔒 until P0 sign-off |
| Phases 3–6 tickets | Written after each phase's P0 design (spec 26) |
| Vertical slice (section 21) | 14 steps: 4 done, 10 left |
| Open decisions (section 36) | 19: 0 closed |
| Readiness checklist (section 23) | 45 items: 2 done, 7 partial, 36 left |

## 2. Phases (spec section 20)

| Phase | What it covers | Status | Done | Left | Blocked by | Exit criterion (spec) |
|---|---|---|---|---|---|---|
| **1** Foundation and hospital onboarding | Stack, organization and facilities, sign-in, staff, departments, credentials, access, audit, CI, provisioning, infrastructure, observability | 🟡 application ~98%, cloud ~10% | 77 tickets (PR #1–#37, #30 and HIMS-OPS-009) | 15 buildable items (section 4a); cloud items | Cloud part: AWS (deferred) | Hospital configured, staff onboarded, isolation enforced |
| **2** Patients and outpatient care | Registration, MPI and duplicates, search, appointments and OPD, encounters, notes, diagnoses, allergies, vitals, reports | ⬜ design drafted | P0 design (PR #28) | Sign-off, then slices 2A–2D (20 tickets) | PO + doctor sign-off (D1–D26); LEGAL before real patient data | Patients and outpatient visits end to end |
| **3** Inpatient and nursing | Admission/discharge, bed allocation, transfers, nursing assessments, care tasks, vital charts, handovers, diet, housekeeping | ⬜ | Bed and ward inventory already built in Phase 1 | P0 design, then build | Phase 2; CLIN | Stays, bed movements and daily care traceable |
| **4** Medication, pharmacy, diagnostics | Drug catalog, prescriptions, pharmacy stock, eMAR, lab orders and results, imaging, safety checks | ⬜ | — | P0 design, then build | Phase 3; CLIN; VENDOR (drug database, LIS, PACS) | Orders, dispensing, administration and results distinct and auditable |
| **5** Insurance and revenue cycle | Payers, Stedi, eligibility, authorizations, charges, invoices, payments, claims, denials, Indian TPAs | ⬜ | Numbering for invoices and claims (Phase 1) | P0 design, then build | Phases 2–4; PAYER; LEGAL (tax) | Services, payer obligations and balances reconcile |
| **6** Integrations and rollout | Patient portal, reporting, FHIR, ABDM, PACS/LIS/devices, performance, security and recovery tests, UAT, rollout | ⬜ | — | All | Earlier phases; partners; AWS | Agreed operational, clinical, security and recovery acceptance tests pass |

## 3. Spec sections (1–36)

| § | Section | Status | What is left | Blocked by |
|---|---|---|---|---|
| 1 | Executive summary | ✅ | — | — |
| 2 | Principles | 🟡 | Principles 2, 3, 7, 10, 12 apply with clinical domains | Domains, CLIN |
| 3 | Personas (16) | 🟡 7 system roles | Clinical roles' permissions | CLIN (approve RBAC document) |
| 4 | Functional domains (25) | 🟡 | See section 5 below | Mostly CLIN, P0 |
| 5 | Clinical workflows | ⬜ | Admission, medication, claim flows | Domains |
| 6 | Technical architecture | 🟡 | S3-compatible storage adapter; integration gateway | AWS; PAYER/VENDOR |
| 7 | Dedicated deployment | 🟡 | Control plane, export/retirement, cross-hospital reporting | AWS, PO, LEGAL |
| 8 | Repository layout | ✅ | — | — |
| 9 | Data modelling | 🟡 | Patient and clinical tables | P0 per domain |
| 10 | Concurrency | 🟡 | Bed allocation race; domain duplicates | P0 ADT, domains |
| 11 | Insurance and Stedi | ⬜ | All | PAYER |
| 12 | Interoperability (FHIR, ABDM) | ⬜ | All | Partners, LEGAL |
| 13 | Security and privacy | 🟡 | Passkeys; error text in traces (HIMS-SEC-020); patient scope; break-glass | 🔓 partly; CLIN; AWS |
| 14 | Redis/Celery | 🟡 | Queue monitoring and alarms | AWS |
| 15 | React frontend | 🟡 1 of 7 workspaces | Clinical workspaces; patient chart | Domains |
| 16 | REST API | 🟡 4 of 18 endpoint groups | Domain endpoints | Domains |
| 17 | AWS deployment | ⬜ | All | AWS (deferred) |
| 18 | Non-functional | 🟡 | SLO measurement; cloud metrics and alarms | 🔓 partly; AWS |
| 19 | Testing | 🟡 | Clinical validation | 🔓 partly; CLIN |
| 20 | Roadmap | 🟡 Phase 1 | Phases 1 (rest) to 6 | See section 2 |
| 21 | Vertical slice (14 steps) | 🟡 4 done | Steps 5–14 | Phases 2–5 |
| 22 | Architecture decisions | 🟡 | Approve ADR-009 to ADR-023 | PO / security |
| 23 | Readiness checklist (45) | 🟡 2 done, 7 partial | 36 items | CLIN, LEGAL, AWS, PAYER |
| 24 | Reference links | n/a | — | — |
| 25 | Delivery standard | 🟡 | Formal requirement records for built features | 🔓 |
| 26 | P0 before each domain | 🟡 | Phase 2 sign-off; P0 for Phases 3–6 | PO, CLIN |
| 27 | P1 before production | ⬜ | Cloud disaster recovery (local restore drills done, HIMS-OPS-009), runbooks, load tests, UAT | AWS, CLIN |
| 28 | Artifact A (data) | 🟡 70% | Volume index check; P0 domains | 🔓 partly; P0 |
| 29 | Artifact B (API) | 🟡 60% | Per-endpoint contract docs; webhooks/adapters | 🔓 partly; PAYER |
| 30 | Artifact C (AWS) | ⬜ 5% | Terraform, network, KMS, backups | AWS |
| 31 | Environments | 🟡 | Hosted Dev/QA/Staging/Production | PO (hosting accounts) |
| 32 | GitHub workflow | 🟡 | Projects board | — |
| 33 | CI/CD | 🟡 | Deploy pipelines | AWS / hosting |
| 34 | Cost strategy | 🟡 | Stages B–D | AWS |
| 35 | Definition of done | 🟡 | Environment and QA evidence | AWS |
| 36 | Open decisions (19) | ⬜ 0 of 19 | All 19 decisions | PO, LEGAL, CLIN, Finance |

## 4. Order of work, step by step

Rule used for the order: finish what can be built now in Phase 1 (production readiness first),
then each later phase as soon as its blocker clears. Blocked items are listed where they will
fit, so nothing is forgotten.

### 4a. Phase 1: buildable now (🔓), in order

| Step | Spec § | Ticket | Task | Status | Why this order |
|---|---|---|---|---|---|
| 1 | 4.3 | HIMS-STAFF-012 | Shift schedules, leave and on-call rotations | ✅ done | Last open part of spec 4.3; nurses and doctors need rotas before Phase 2 scheduling |
| 2 | 4.3, 13.2 | HIMS-STAFF-008 | Department-scoped staff directory (see only your departments' staff) | ✅ done | Privacy: least access |
| 3 | 13.5, 19.1 | HIMS-SEC-019 | Secret-in-logs test (no password, token or key ever reaches a log) | ✅ done | One of the 10 security tests in spec 13.5 |
| 4 | 13.5, 23 | HIMS-OPS-009 | Backup and restore drill, local (with audit chain and relationship checks) | ✅ done | Spec 13.5 restore test; needed before any real data |
| 5 | 13, 17.6 | HIMS-OPS-007 | Separate database users: app, migrations, read-only (the app cannot erase the audit log) | ⬜ | Defence in depth; can be set up locally |
| 6 | 14.3 | HIMS-PLAT-014 | Outbox clean-up job and runbook (idempotency part done) | 🟡 | Keeps tables small |
| 7 | 6.2, 17 | HIMS-OPS-010 | Serve admin and API-docs static files in hosted environments (WhiteNoise) | ⬜ | Needed for the first hosted environment |
| 8 | 13.1 | HIMS-SEC-015 | Admin console address allow-list (setting; firewall later) | ⬜ | Before the console is reachable outside this computer |
| 9 | 4.10, 15.1 | HIMS-FAC-008 | Bed board: every ward's beds and their status on one screen (no patients yet) | ⬜ | Ready for Phase 3 admissions |
| 10 | 4.12 | HIMS-FAC-009 | Equipment register (what, where, status, service dates) | ⬜ | Only the register; workflows wait for PO |
| 11 | 4.1 | HIMS-ORG-006 | Hospital logo and letterhead for printouts and emails | ⬜ | Needed by Phase 2 visit summaries |
| 12 | 4.23 | HIMS-NOTIF-003 | Hospital-editable message templates (patient opt-out comes with Phase 2) | ⬜ | Before patient emails in slice 2B |
| 13 | 28.6 | HIMS-DATA-002 | Index check with production-like synthetic volume | ⬜ | Before real volume |
| 14 | 19.2 | HIMS-QA-003 | Browser tests for the US deployment and the admin console | ⬜ | US is a separate deployment |
| 15 | 13.1 | HIMS-IAM-014 | Passkeys as a second factor | ⬜ | Optional upgrade over authenticator codes |
| 16 | 25, 29 | HIMS-DOC-001 | Requirement records and per-endpoint contract docs for built features | ⬜ | Traceability (spec 25.3, 29) |
| 17 | 18 | HIMS-OPS-017 | Response-time targets (SLOs) measured locally | ⬜ | Baseline before hosting |
| 18 | 4.22, 13.3 | HIMS-SEC-013 | Virus scanning of uploaded documents | ⬜ | Before patient documents |
| 19 | 13.3, 18 | HIMS-SEC-020 | Filter the error text kept in traces with the same rules as logs | ⬜ | Gap found by HIMS-SEC-019; needed before traces are sent anywhere (HIMS-PLAT-019) |
| — | 4.4 | HIMS-IAM-019 | Self-service cover requests | ⬜ optional | When hospitals ask |
| — | 4.3 | HIMS-STAFF-014 | Shift swaps requested by staff, approved by the head | ⬜ optional | When hospitals ask |
| — | 4.25 | HIMS-SEC-017 | Integrity check as a background job | ⬜ later | When the audit log nears ~1 million records |
| — | 19.2 | HIMS-QA-002 | Make browser tests a required check | ⬜ PO | You, in the GitHub branch rules |

### 4b. Phase 1: blocked (🔒)

| Spec § | Ticket | Task | Blocked by |
|---|---|---|---|
| 17, 30 | HIMS-OPS-003 | Terraform modules (network, ECS, RDS, Redis, S3, KMS, secrets, monitoring) | AWS |
| 17, 18 | HIMS-OPS-004 | Alarms and runbooks (errors, latency, database, queues, outbox) | AWS |
| 33 | HIMS-OPS-005 | Deploy pipeline with build once, promote to QA, Staging, Production | AWS / hosting |
| 33 | HIMS-OPS-006 | Migration release job with a lock; schema version per hospital | AWS / hosting |
| 7 | HIMS-OPS-008 | Hospital provisioning automation (control plane) | AWS |
| 4.23 | HIMS-OPS-011 | Real email provider per hosted environment | AWS / hosting |
| 4.22 | HIMS-OPS-015 | S3 document storage (KMS, versioning) | AWS |
| 13.4 | HIMS-SEC-016 | Copy the audit chain head to write-once storage | AWS |
| 17.3, 27.1 | HIMS-OPS-018 | Restore drill of a cloud snapshot with the same checks (gap found in HIMS-OPS-009) | AWS |
| 13.3 | HIMS-SEC-018 | Send the screens' protection headers at hosting | AWS |
| 18 | HIMS-PLAT-019 | Send traces to AWS | AWS |
| 4.23 | HIMS-NOTIF-002 | SMS gateway (India DLT, US provider) | VENDOR |
| 4.4, 36 | HIMS-IAM-008 | Single sign-on (OIDC/SAML) | PO decision (section 36) |
| 4.4 | HIMS-IAM-018 | Clinical delegation | CLIN |
| 4.3 | — | Clinical privileges (what a doctor may perform) | CLIN |
| 4.3 | HIMS-STAFF-013 | Leave balances and entitlements | PO (HR leave policy) |
| 4.3 | HIMS-STAFF-015 | Minimum staffing per shift, gap alerts | CLIN (staffing ratios) |
| 3 | — | Approve the RBAC document, clinical role permissions | CLIN |
| 4.25 | HIMS-COMP-006 | Retention purge with legal hold | LEGAL (periods) |
| 23 | HIMS-COMP-001…005 | Counsel and hospital review of the compliance pack | LEGAL |
| 23 | HIMS-SEC-011 | Security reviewer for the threat model | Security reviewer |
| 4.1 | — | Tax rules | LEGAL |

### 4c. Phase 2 onwards

| Step | Phase | Spec § | Tickets | Task | Status | Blocked by |
|---|---|---|---|---|---|---|
| 19 | 2 | 26 | HIMS-PAT-000 | Sign off the Phase 2 P0 design (26 decisions) | 🟡 waiting | **PO + doctor**; LEGAL items D6, D7, D9, D18, D24 before real data |
| 20 | 2 | 4.5, 13 | HIMS-PAT-001, 002, 005, 006; HIMS-IAM-010; HIMS-DATA-003 | Slice 2A: registration with MRN, search, chart header, restricted records, patient scope | ⬜ | Step 19 |
| 21 | 2 | 4.6, 4.23 | HIMS-OPD-001…004 | Slice 2B: schedules (uses step 1 rotas), appointments without double booking, walk-ins, queue, reminders | ⬜ | Step 20 |
| 22 | 2 | 4.7, 4.8 | HIMS-CLIN-001…007; HIMS-IAM-011, 020 | Slice 2C: visits, vitals, allergies, diagnoses (ICD), notes with sign/amend, emergency access, confirm-it's-you for clinical actions | ⬜ | Step 21; CLIN (terminology) |
| 23 | 2 | 4.5, 4.24 | HIMS-PAT-003, 004; HIMS-RPT-001, 002 | Slice 2D: duplicates and merge, visit summary, OPD lists; Phase 2 exit check | ⬜ | Step 22 |
| 24 | 3 | 26 | — | Phase 3 P0 design (admission, discharge, transfer, nursing, diet) | ⬜ | Phase 2; CLIN |
| 25 | 3 | 4.7, 4.10, 10.1 | — | Admission, discharge, bed allocation (no double allocation), transfers | ⬜ | Step 24 |
| 26 | 3 | 4.9 | — | Nursing assessments, care tasks, vital charts, handovers (uses step 1 shifts) | ⬜ | Step 24; CLIN |
| 27 | 3 | 4.11, 4.12 | — | Diet orders and kitchen; housekeeping turnaround; transport | ⬜ | Step 24; CLIN, PO |
| 28 | 4 | 26 | — | Phase 4 P0 design | ⬜ | Phase 3; CLIN |
| 29 | 4 | 4.13, 4.20 | — | Drug catalog, prescriptions, pharmacy stock and dispensing | ⬜ | VENDOR (drug database), CLIN |
| 30 | 4 | 4.14 | — | Medication administration record (eMAR) | ⬜ | Step 29; CLIN |
| 31 | 4 | 4.15 | — | Lab orders, specimens, results | ⬜ | VENDOR (LIS), CLIN |
| 32 | 4 | 4.16 | — | Imaging orders and reports | ⬜ | VENDOR (PACS), CLIN |
| 33 | 4 | 4.17 | — | Procedures, surgery, anaesthesia, ICU (placed in Phase 4; section 20 does not name a phase) | ⬜ | CLIN |
| 34 | 5 | 26, 11 | — | Phase 5 P0 design; insurance scope decision | ⬜ | PAYER, Finance |
| 35 | 5 | 4.18, 11 | — | Payers, Stedi eligibility, authorizations, claims, remittance, denials; Indian TPAs and schemes | ⬜ | PAYER |
| 36 | 5 | 4.19, 4.20 | — | Charges, invoices (GST numbering already built), payments, reconciliation, accounting | ⬜ | LEGAL (tax), Finance |
| 37 | 6 | 4.21 | — | Patient and caregiver portal | ⬜ | Phase 2+ |
| 38 | 6 | 4.24, 7.6 | — | Reporting and analytics | ⬜ | Domains; LEGAL for cross-hospital |
| 39 | 6 | 12 | — | FHIR, ABDM (ABHA), external EHRs | ⬜ | Partners, LEGAL |
| 40 | 6 | 4.15, 4.16 | — | PACS, LIS and device integrations | ⬜ | VENDOR |
| 41 | 6 | 17, 27, 30 | Phase 1 🔒 AWS items | AWS stage: hosting, backups, disaster recovery, alarms (you chose to do this later) | ⬜ | AWS |
| 42 | 6 | 18, 19, 27 | — | Performance, security and recovery tests; clinical validation | ⬜ | Hosting, CLIN |
| 43 | 6 | 20, 35 | — | Hospital acceptance testing, training, controlled rollout | ⬜ | Everything above |

**Cross-cutting, at any time:** close the 19 decisions in section 36 (owner per row), approve
ADR-009 to ADR-023, and work through the 45-item readiness checklist (section 23).

## 5. Functional domains (section 4)

| § | Domain | Phase | Status | Left (🔓 now / 🔒 blocked) |
|---|---|---|---|---|
| 4.1 | Hospital and branches | 1 | 🟡 94% | 🔓 logo/letterhead · 🔒 tax rules (LEGAL) |
| 4.2 | Departments | 1 | 🟡 85% | 🔒 pricing, slots, escalation (CLIN) |
| 4.3 | Staff and credentials | 1 | 🟡 99% | ✅ shifts, leave, on-call · 🔒 clinical privileges (CLIN), leave balances (PO), minimum staffing (CLIN) |
| 4.4 | Identity and access | 1 | 🟡 99% (department-level staff view done) | 🔒 SSO (PO), break-glass (Phase 2) |
| 4.5 | Patient registration and MPI | 2 | ⬜ designed | 🔒 sign-off |
| 4.6 | Appointments and OPD | 2 | ⬜ designed | 🔒 sign-off |
| 4.7 | Encounters and admissions | 2, 3 | ⬜ outpatient part designed | 🔒 sign-off; Phase 3 P0 |
| 4.8 | EHR/EMR | 2 | ⬜ | 🔒 CLIN |
| 4.9 | Nursing | 3 | ⬜ | 🔒 CLIN |
| 4.10 | Beds and wards | 1, 3 | 🟡 40% | 🔓 bed board · 🔒 allocation (Phase 3) |
| 4.11 | Diet and kitchen | 3 | ⬜ | 🔒 CLIN |
| 4.12 | Housekeeping, equipment, transport | 1, 3 | ⬜ | 🔓 equipment register · 🔒 workflows (PO) |
| 4.13 | Pharmacy | 4 | ⬜ | 🔒 CLIN, VENDOR |
| 4.14 | eMAR | 4 | ⬜ | 🔒 CLIN |
| 4.15 | Laboratory | 4 | ⬜ | 🔒 CLIN, VENDOR |
| 4.16 | Radiology | 4 | ⬜ | 🔒 CLIN, VENDOR |
| 4.17 | Surgery, anaesthesia, ICU | 4 | ⬜ | 🔒 CLIN |
| 4.18 | Insurance and payers | 5 | ⬜ | 🔒 PAYER |
| 4.19 | Billing and revenue cycle | 5 | ⬜ | 🔒 LEGAL, PAYER |
| 4.20 | Procurement, inventory, accounting | 4, 5 | ⬜ | 🔒 PO (finance rules) |
| 4.21 | Patient portal | 6 | ⬜ | 🔒 needs 4.5+ |
| 4.22 | Documents and consent | 1, 2 | 🟡 20% | 🔓 virus scanning · 🔒 S3 (AWS), consent forms (LEGAL) |
| 4.23 | Notifications | 1, 2 | 🟡 60% | 🔓 editable templates · 🔒 SMS (VENDOR) |
| 4.24 | Reporting | 2–6 | ⬜ | 🔒 needs domains |
| 4.25 | Audit and governance | 1 | 🟡 90% | 🔒 retention periods (LEGAL), write-once copy (AWS) |

## 6. Done so far

77 Phase 1 tickets, delivered in PR #1–#37 (and #30), and the HIMS-OPS-009 PR. The full list with what each PR did is in the
tracker's [PR history](spec-status.md#pr-history-traceability-spec-253) and
[work queue](spec-status.md#next-work-queue-dependency-free-in-recommended-order).

New tickets named here for the first time (HIMS-SEC-019, HIMS-FAC-008, HIMS-FAC-009,
HIMS-ORG-006, HIMS-DOC-001, HIMS-OPS-017, and HIMS-SEC-020 and HIMS-OPS-018 added on 2026-11-08) are
also in the Phase 1 backlog.
