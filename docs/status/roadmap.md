# HIMS roadmap: what is done, what is left, and in what order

Built from [HIMS_Architecture_Specification_v2.MD](../../HIMS_Architecture_Specification_v2.MD)
section 20 (phases), 4 (domains), 21 (vertical slice), 26–27 (P0/P1), 36 (decisions), and from the
[tracker](spec-status.md) and backlogs ([Phase 1](../backlog/phase-1-foundation.md),
[Phase 2](../backlog/phase-2-patients.md)). The tracker stays the detailed record; this page is the
ordered plan. **Last updated:** 2026-11-10 (after PR #47, with the retention purge built).
**Update 2026-11-12:** supplier support access (HIMS-IAM-021) and the ten demo hospitals
(HIMS-QA-004) built as group 9; the counts below are corrected where marked "2026-11-12".
**Update 2026-11-12, later:** the free Development environment is live (HIMS-OPS-024 done:
Render + Neon + cron-job.org, https://hims-dev.onrender.com). **Phase 1's application part is
finished**; what is left of Phase 1 is the hosting stage at the end, 4 optional items and 2 PO
deferrals, none of which blocks Phase 2. **Next: Phase 2, Slice 2A, HIMS-PAT-001** (section 4c).
**Update 2026-11-12, Phase 2 started:** HIMS-PAT-001 done (patient registration with MRN, contacts, people, ID numbers encrypted and masked, consents; screens, console, roles, demo patients). **Next: Phase 2 → Spec §4.5, §13 → Slice 2A → HIMS-PAT-002** (patient search).

**Update 2026-11-13:** HIMS-PAT-002 done (patient search: MRN, phone, ID number or a name by similar spelling and sound, any order, earlier names; at most 50 minimal results; every search audited; console search; demo examples; demo records can also fill the hosted Development hospital). **Next: Phase 2 → Spec §4.5, §13 → Slice 2A → HIMS-PAT-005** (patient chart header and overview).

**Update 2026-11-14:** HIMS-PAT-005 done (patient chart: header always in view with the allergy status and flags, alerts, Overview / Demographics / History tabs; History shows medical records who opened and changed the record, audited; console Chart section; demo chart-alert patients). **Next: Phase 2 → Spec §4.5, §13 → Slice 2A → HIMS-PAT-006** (restricted VIP/staff records and emergency access with review).

**Update 2026-11-14, later:** HIMS-PAT-006 done (restricted VIP/staff records hidden from search, opened only by medical records or with emergency access: 4 hours, reason, emailed, reviewed by someone else; restricted openings listed; console; demo, with a top-up command for the hosted hospital). HIMS-PAT-008 added (weekly review email). HIMS-IAM-010 (patient scope by treating team) needs visits, so it moves to slice 2C with HIMS-CLIN-001. **Next: Phase 2 → Spec §28, §4.5 → Slice 2A → HIMS-DATA-003** (Artifact A for patients/MPI: the reviewed data architecture of the patient domain, the last buildable item of slice 2A).

**Update 2026-11-14, latest:** HIMS-DATA-003 done: the patient / MPI domain reviewed against spec 28.8 and accepted ([review](../architecture/data-architecture/patients-mpi-review.md)): the volume check now holds 500,000 invented patients (5.9 million rows in all) and checks 15 patient queries and 10 patient screens plus 2 console lists; it found and fixed **seven problems**: no index for the newest-patients list (306 ms, screen 611 ms), the MRN number part read every MRN by pattern (400 ms), earlier MRNs and the previous-MRN hospitals read whole tables, the exact MRN look-up did not name the hospital (hidden by PostgreSQL 18's skip scan on the PC; CI and hosting run 17), the hospital's time zone was read once per row (61 queries for a name search, 107 for the console's emergency access list) and the console's patient and issued-number lists sorted or counted whole tables (1.1 s; 513 ms); a search's total is counted up to 1,000 ("more than 1,000"). Migrations `patients.0004` and `numbering.0002` (indexes built `CONCURRENTLY`). Every database rule on the patient tables is broken on purpose by `test_data_invariants.py` (11 tests; a new rule without a test fails). Performance screen groups results by area (Patients, Audit log, …); console page **Restricted record openings** (missed in HIMS-PAT-006's console); demo hospitals record an index check. Follow-ups: HIMS-PAT-009 (name search at 10× the register), HIMS-IAM-023 (reporting user and patient data), HIMS-DATA-004 (Artifact A for the later P0 domains). **Slice 2A (step 20) is complete. Next: Phase 2 → Spec §4.6 → Slice 2B → HIMS-OPD-001** (doctor schedules and exceptions), then OPD-002 (appointments), OPD-003 (walk-ins and queue), OPD-004 (reminders).

**Update 2026-11-15:** HIMS-OPD-001 done: **doctor schedules and exceptions** ([how-to](../workflows/doctor-schedules.md), [record](../requirements/outpatient.md), [data design and Artifact A review](../architecture/data-architecture/scheduling.md), [ADR-038](../decisions/ADR-038-opd-sessions-and-free-slots.md)): new app `apps/scheduling` (tables `doctor_schedules`, `schedule_exceptions`; migration `scheduling.0001`); screen **Doctor schedules**: one department's week with each doctor's OPD sessions and free slots; weekly sessions on several weekdays (slot 5–120 minutes, up to 20 extra bookings, D11), changed or ended (days and hours never edited); doctor away (all day or part), holiday (a department, or the whole facility with a facility grant), extra session, each answering with the sessions it takes off; **leave approved on the Leave page takes sessions off by itself** (the step 1 rotas; leave asked shows "Leave asked"); suspended doctors' sessions show off; a posting or employment that ends ends them; no overlap for one doctor in any department (service under a row lock and a database exclusion constraint). New permissions `appointments.view`, `schedules.manage`; new role **OPD scheduler**; the head of department, branch administrator and front desk (view only; never why a doctor is away) get them; doctors see their own sessions on My schedule. Admin console: Doctor schedules and Schedule exceptions with the same rules, plus **Leave balances** (missed from HIMS-STAFF-013's console). Feature **Appointments and outpatient visits** live per facility. Every database rule has a test (`test_schedule_invariants.py`); four queries and two screens in the volume check (area Outpatient (OPD)). Demo: sessions and every kind of exception per branch and an `opd.<branch>@` account; `add_demo_doctor_schedules` for the hosted hospital. Follow-ups: HIMS-OPD-002 notes (booked patients when sessions go off, slot changes under bookings, the Leave page's approval), new HIMS-OPD-005 (other clinicians' clinics, PO to decide). Decisions log rows 37–40. **Step 21 (slice 2B) started. Next: Phase 2 → Spec §4.6 → Slice 2B → HIMS-OPD-002** (appointments without double booking, reschedule, cancel), then OPD-003 (walk-ins and queue), OPD-004 (reminders).

**Update 2026-11-15, later:** HIMS-OPD-002 done: **appointments without double booking, reschedule, cancel** ([how-to](../workflows/appointments.md), [record](../requirements/outpatient.md#hims-opd-002), [data design, part 2](../architecture/data-architecture/scheduling.md#part-2-appointments-hims-opd-002), [ADR-039](../decisions/ADR-039-appointments-no-double-booking.md)): table `appointments` (migration `scheduling.0002`); screen **Appointments** (a department's day, free and booked slots, book from a slot or the chart's **Book** button, over the slots as the session allows, move with a link to the old one, cancel with the reason); **the database refuses double booking**, even for two bookings at the same moment; a **To move** list of booked patients whose doctor is away, on approved leave, on holiday or whose session ended (the exception's answer and the Leave page show them too); the chart's Overview shows the next appointment and My schedule the booked counts. New permission `appointments.manage` (front desk and OPD scheduler); console Appointments with a Move page and an Appointments to move page; invariant tests; volume check at one million appointments; demo examples per branch and `add_demo_appointments` for the hosted hospital. New tickets HIMS-OPD-006 (waitlist, PO to decide) and HIMS-OPD-007 (referrals). Decisions log rows 41–44. **Next: Phase 2 → Spec §4.6 → Slice 2B → HIMS-OPD-003** (walk-ins, tokens and the OPD queue; no-show job), then HIMS-OPD-004 (reminders).

**Update 2026-11-15, latest:** HIMS-OPD-003 done: **walk-ins, tokens and the OPD queue; no-show job** ([how-to](../workflows/opd-queue.md), [record](../requirements/outpatient.md#hims-opd-003), [data design and Artifact A review, part 3](../architecture/data-architecture/scheduling.md#part-3-the-opd-queue-hims-opd-003), [ADR-040](../decisions/ADR-040-opd-queue-tokens-and-no-shows.md)): new columns on `appointments` (migration `scheduling.0003`: token, checked in when and by whom, called in, seen; source walk-in; cancel reason left before being seen); screen **OPD queue**: one department's doctors today on the hospital's clock, each with their patients by token (waiting minutes, with the doctor, seen, still to come, did not come); **check-in** gives the doctor's next token in arrival order (a late patient marked did not come too, the same day); **walk-ins** are checked in at once in the doctor's session today and take **no slot** (the no-double-booking rule rebuilt without them); **Call next** (the lowest waiting token in; whoever was with the doctor seen), **Seen**, **Left before being seen**; a **job every 15 minutes** (`opd-no-shows`) marks booked patients of ended sessions as did not come (also off the To move list); the front desk marks one once its time has passed and undoes it before the session ends; the database refuses a token twice for a doctor's day and a checked-in appointment without its token; restricted records checked in only by those who may open them; the Appointments page shows the token; console: **OPD queue** page (Call next per doctor, walk-in form) and five actions; invariant tests for the four new rules; volume check: three queries and one screen at one million appointments; demo: today's queue per branch and `add_demo_opd_queue` for the hosted hospital. P0's facility day index not added (the queue is per department). New ticket HIMS-OPD-008 (waiting-room token display, PO to decide); notes on HIMS-CLIN-001 (visit number at check-in; the doctor's start and finish replace Call next and Seen), HIMS-CLIN-007, HIMS-RPT-002, HIMS-OPD-004. Decisions log rows 45–48. **Next: Phase 2 → Spec §4.6, §4.23 → Slice 2B → HIMS-OPD-004** (email confirmations and reminders), the last ticket of slice 2B.

**2026-11-08 decisions** ([decisions log](decisions-log.md)): CLIN, LEGAL and PO approved the pending documents
**for now** (roles and permissions, compliance pack, Phase 2 design); SMS stays on the console; the security review
comes at the end of Phase 1; hosting is **Oracle Cloud at the very end** instead of AWS
([ADR-027](../decisions/ADR-027-hosting-on-oracle-cloud.md)). Below, 'AWS' therefore means the **hosting stage at
the end**, re-planned by the hosting analysis (HIMS-OPS-020, done): a free Development environment on a host that needs no payment card first ([ADR-034](../decisions/ADR-034-free-hosting-without-a-card.md)), paid hosting before real data.

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
| Phases not started | 5 (Phase 2 design approved for now on 2026-11-08: it can be built) |
| Spec sections (1–36) | 36: ✅ 2 · 🟡 27 · ⬜ 6 · not applicable 1 (section 24, links) |
| Functional domains (section 4.1–4.25) | 25: 🟡 9 started · ⬜ 16 not started |
| Phase 1 tickets (2026-11-12, after HIMS-OPS-024) | 129: ✅ 103 done or approved (98 Done + 5 compliance documents approved for now) = 80% · 26 left, none blocking Phase 2: 4 🔓 optional (HIMS-IAM-019, HIMS-STAFF-014, HIMS-SEC-017, HIMS-QA-002), 15 hosting stage at the end (paid hosting / AWS), 2 deferred by the PO (SMS gateway, single sign-on), 5 moved to Phase 2 |
| Phase 1 tickets (2026-11-12) | 129: ✅ 102 done or approved (97 Done + 5 compliance documents approved for now) · 27 left: 4 🔓 optional, 16 hosting stage (HIMS-OPS-024 in progress; HIMS-OPS-025 owner console new), 2 deferred by the PO, 5 moved to Phase 2 (HIMS-IAM-010, -011, -018, -020, HIMS-DATA-003) |
| Phase 1 tickets | 126: ✅ 103 done or approved · 23 left: 4 🔓 can be built now (all optional or later), 15 hosting stage (now: the free Development environment on Render + Neon, HIMS-OPS-024), 2 deferred by the PO (SMS gateway, single sign-on), 2 moved to Phase 2 and 5 |
| Phase 2 tickets (already written) | 22: all ⬜; buildable after the Phase 1 queue (P0 approved for now 2026-11-08) |
| Phase 2 tickets (2026-11-12, after HIMS-PAT-001) | 24 (2 gaps added: HIMS-PAT-007 recording a death, HIMS-IAM-022 supplier support and patient records): ✅ 1 done (HIMS-PAT-001) + the P0 sign-off (HIMS-PAT-000) approved for now · 22 left · **2026-11-13:** ✅ 2 done (HIMS-PAT-001, HIMS-PAT-002) · 21 left · **2026-11-14:** ✅ 3 done (HIMS-PAT-001, -002, -005) · 20 left · **2026-11-14, later:** 25 (HIMS-PAT-008 added): ✅ 4 done (HIMS-PAT-001, -002, -005, -006) · 21 left · **2026-11-14, latest:** 28 (HIMS-PAT-009, HIMS-IAM-023, HIMS-DATA-004 added): ✅ 4 done (HIMS-PAT-001, -002, -005, -006) · 24 left; HIMS-DATA-003 (moved from Phase 1) ✅ done, so Phase 1 is ✅ 104 of 129 (99 Done + 5 approved) · **2026-11-15:** 29 (HIMS-OPD-005 added): ✅ 5 done (HIMS-PAT-001, -002, -005, -006, HIMS-OPD-001) · 24 left · **2026-11-15, later:** 31 (HIMS-OPD-006, -007 added): ✅ 6 done (HIMS-PAT-001, -002, -005, -006, HIMS-OPD-001, -002) · 25 left · **2026-11-15, latest:** 32 (HIMS-OPD-008 added): ✅ 7 done (HIMS-PAT-001, -002, -005, -006, HIMS-OPD-001, -002, -003) · 25 left |
| Phases 3–6 tickets | Written after each phase's P0 design (spec 26) |
| Vertical slice (section 21) | 14 steps: 4 done, 10 left |
| Open decisions (section 36) | 19: 0 closed |
| Readiness checklist (section 23) | 45 items: 2 done, 7 partial, 36 left |

## 2. Phases (spec section 20)

| Phase | What it covers | Status | Done | Left | Blocked by | Exit criterion (spec) |
|---|---|---|---|---|---|---|
| **1** Foundation and hospital onboarding | Stack, organization and facilities, sign-in, staff, departments, credentials, access, audit, CI, provisioning, infrastructure, observability | 🟡 application done, cloud ~20% (2026-11-12: 102 of 129 = 79%; free Development environment live on Render + Neon, HIMS-OPS-024 nearly done; supplier support access and demo hospitals added; later 2026-11-12: HIMS-OPS-024 done, 103 of 129 = 80%, application part finished, only the hosting stage at the end left) | 103 (PR #1–#52 and #30, ready for Northflank, 2 approvals) | The free Development environment on Northflank (HIMS-OPS-024); 4 optional items | Hosting: free Development without a card first (ADR-034); paid hosting before real data | Hospital configured, staff onboarded, isolation enforced |
| **2** Patients and outpatient care | Registration, MPI and duplicates, search, appointments and OPD, encounters, notes, diagnoses, allergies, vitals, reports | ⬜ design approved for now (2026-11-08) | P0 design (PR #28) and its sign-off | Slices 2A–2D (20 tickets) | Nothing; starts after the Phase 1 queue | Patients and outpatient visits end to end · **2026-11-12: 🟡 started**, HIMS-PAT-001 done (registration with MRN) |
| **3** Inpatient and nursing | Admission/discharge, bed allocation, transfers, nursing assessments, care tasks, vital charts, handovers, diet, housekeeping | ⬜ | Bed and ward inventory already built in Phase 1 | P0 design, then build | Phase 2; CLIN | Stays, bed movements and daily care traceable |
| **4** Medication, pharmacy, diagnostics | Drug catalog, prescriptions, pharmacy stock, eMAR, lab orders and results, imaging, safety checks | ⬜ | — | P0 design, then build | Phase 3; CLIN; VENDOR (drug database, LIS, PACS) | Orders, dispensing, administration and results distinct and auditable |
| **5** Insurance and revenue cycle | Payers, Stedi, eligibility, authorizations, charges, invoices, payments, claims, denials, Indian TPAs | ⬜ | Numbering for invoices and claims (Phase 1) | P0 design, then build | Phases 2–4; PAYER; LEGAL (tax) | Services, payer obligations and balances reconcile |
| **6** Integrations and rollout | Patient portal, reporting, FHIR, ABDM, PACS/LIS/devices, performance, security and recovery tests, UAT, rollout | ⬜ | — | All | Earlier phases; partners; AWS | Agreed operational, clinical, security and recovery acceptance tests pass |

## 3. Spec sections (1–36)

| § | Section | Status | What is left | Blocked by |
|---|---|---|---|---|
| 1 | Executive summary | ✅ | — | — |
| 2 | Principles | 🟡 | Principles 2, 3, 7, 10, 12 apply with clinical domains | Domains, CLIN |
| 3 | Personas (16) | 🟡 7 system roles | Clinical roles' permissions, built with Phase 2 | — (RBAC document approved for now, 2026-11-08) |
| 4 | Functional domains (25) | 🟡 | See section 5 below | Mostly CLIN, P0 |
| 5 | Clinical workflows | ⬜ | Admission, medication, claim flows | Domains |
| 6 | Technical architecture | 🟡 | S3-compatible storage adapter; integration gateway (static files served by the app: done, HIMS-OPS-010) | AWS; PAYER/VENDOR |
| 7 | Dedicated deployment | 🟡 | Control plane, export/retirement, cross-hospital reporting | AWS, PO, LEGAL |
| 8 | Repository layout | ✅ | — | — |
| 9 | Data modelling | 🟡 | Patient and clinical tables | P0 per domain |
| 10 | Concurrency | 🟡 | Bed allocation race; domain duplicates | P0 ADT, domains |
| 11 | Insurance and Stedi | ⬜ | All | PAYER |
| 12 | Interoperability (FHIR, ABDM) | ⬜ | All | Partners, LEGAL |
| 13 | Security and privacy | 🟡 | Patient scope; break-glass (Phase 2); independent penetration test (HIMS-SEC-021). Done: passkeys (HIMS-IAM-014), error text in traces (HIMS-SEC-020), virus scanning (HIMS-SEC-013), console allow-list (HIMS-SEC-015), the Phase 1 security review with session limits, per-account sign-in pause and key rotation (HIMS-SEC-011) | 🔓 partly; CLIN; AWS |
| 14 | Redis/Celery | 🟡 | Alarms on queue health (monitoring and clean-up built, HIMS-PLAT-014) | Hosting stage |
| 15 | React frontend | 🟡 1 of 7 workspaces | Clinical workspaces; patient chart | Domains |
| 16 | REST API | 🟡 4 of 18 endpoint groups | Domain endpoints | Domains |
| 17 | AWS deployment | ⬜ | All, on Oracle Cloud instead (ADR-027) | Hosting stage at the end |
| 18 | Non-functional | 🟡 | Load test (HIMS-OPS-021); cloud metrics and alarms (response-time targets measured locally: HIMS-OPS-017) | AWS |
| 19 | Testing | 🟡 | Clinical validation | 🔓 partly; CLIN |
| 20 | Roadmap | 🟡 Phase 1 | Phases 1 (rest) to 6 | See section 2 |
| 21 | Vertical slice (14 steps) | 🟡 4 done | Steps 5–14 | Phases 2–5 |
| 22 | Architecture decisions | 🟡 | Review ADR-009 to ADR-027 one by one (accepted for now, 2026-11-08) | PO |
| 23 | Readiness checklist (45) | 🟡 3 done, 7 partial | 35 items | CLIN, LEGAL, AWS, PAYER |
| 24 | Reference links | n/a | — | — |
| 25 | Delivery standard | 🟡 90% | Records for each new requirement as built; release evidence per environment (records for all built ones done, HIMS-DOC-001) | Hosting |
| 26 | P0 before each domain | 🟡 | P0 for Phases 3–6 (Phase 2 approved for now, 2026-11-08) | PO, CLIN |
| 27 | P1 before production | ⬜ | Cloud disaster recovery (local restore drills done, HIMS-OPS-009), runbooks, load tests, UAT | AWS, CLIN |
| 28 | Artifact A (data) | 🟡 85% | P0 domains (volume index check done: HIMS-DATA-002) · **2026-11-14: patients/MPI accepted (HIMS-DATA-003)**; later P0 domains: HIMS-DATA-004 · **2026-11-15: doctor schedules reviewed (HIMS-OPD-001)** · **2026-11-15, later: appointments reviewed (HIMS-OPD-002; one million in the volume check)** · **2026-11-15, latest: the OPD queue reviewed (HIMS-OPD-003)** | P0 |
| 29 | Artifact B (API) | 🟡 85% | Provider adapters and webhooks (per-endpoint contracts done, HIMS-DOC-001) | PAYER, VENDOR |
| 30 | Artifact C (AWS) | 🟡 8% | Terraform, network, KMS, cloud backups (30.5 separate database users done, HIMS-OPS-007) | Hosting stage (Oracle Cloud, ADR-027) |
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

**Built in groups** (PO, 2026-11-09): related tasks share one PR; anything risky goes alone.

| PR | Group | Tasks | Spec § | Status |
|---|---|---|---|---|
| 1 | Hospital setup | HIMS-FAC-009, HIMS-ORG-006, HIMS-NOTIF-003 | 4.12, 4.1, 4.23 | ✅ done |
| 2 | Staff | HIMS-STAFF-016, HIMS-STAFF-015, HIMS-STAFF-013 | 4.3 | ✅ done |
| 3 | Security filters | HIMS-SEC-020, HIMS-SEC-013 | 13.3, 18, 4.22 | ✅ done |
| 4 | Passkeys (alone: changes sign-in) | HIMS-IAM-014 | 13.1 | ✅ done |
| 5 | Retention purge (alone: deletes data) | HIMS-COMP-006 | 4.25, 28 | ✅ done |
| 6 | Measuring and tests | HIMS-DATA-002, HIMS-OPS-017, HIMS-QA-003 | 28, 18, 19.2 | ✅ done |
| 7 | Docs (last: describes everything built) | HIMS-DOC-001 | 25, 29 | ✅ done |
| 8 | Ready for a free host (found by the hosting analysis) | HIMS-OPS-022, HIMS-OPS-023 | 17, 31, 14 | ✅ done |
| 9 | Supplier support access and demo hospitals (PO request 2026-11-12) | HIMS-IAM-021, HIMS-QA-004 (and the console's "Copy a week", HIMS-STAFF-012) | 7.2, 7.4, 13, 19, 31.1 | ✅ done |

**Everything buildable before hosting is done** (the security review, HIMS-SEC-011, was the last step), and the hosting analysis (HIMS-OPS-020) is done. Group 8 (ready for the free host) is done too. **Now: the free Development environment on Render + Neon (HIMS-OPS-024, section 4b), in progress.** The table below keeps each task's own row. **2026-11-12: HIMS-OPS-024 done (live at https://hims-dev.onrender.com); next is Phase 2, Slice 2A (section 4c).**

| Step | Spec § | Ticket | Task | Status | Why this order |
|---|---|---|---|---|---|
| 1 | 4.3 | HIMS-STAFF-012 | Shift schedules, leave and on-call rotations | ✅ done | Last open part of spec 4.3; nurses and doctors need rotas before Phase 2 scheduling |
| 2 | 4.3, 13.2 | HIMS-STAFF-008 | Department-scoped staff directory (see only your departments' staff) | ✅ done | Privacy: least access |
| 3 | 13.5, 19.1 | HIMS-SEC-019 | Secret-in-logs test (no password, token or key ever reaches a log) | ✅ done | One of the 10 security tests in spec 13.5 |
| 4 | 13.5, 23 | HIMS-OPS-009 | Backup and restore drill, local (with audit chain and relationship checks) | ✅ done | Spec 13.5 restore test; needed before any real data |
| 5 | 13.2, 17.2, 30.5 | HIMS-OPS-007 | Separate database users: app, migrations, read-only (the app cannot erase the audit log) | ✅ done | Defence in depth; can be set up locally |
| 6 | 14.3 | HIMS-PLAT-014 | Outbox clean-up job and runbook (idempotency part done) | ✅ done | Keeps tables small |
| 7 | 6.2, 17 | HIMS-OPS-010 | Serve admin and API-docs static files in hosted environments (WhiteNoise) | ✅ done | Needed for the first hosted environment |
| 8 | 13.1 | HIMS-SEC-015 | Admin console address allow-list (setting; firewall later) | ✅ done | Before the console is reachable outside this computer |
| 9 | 4.10, 15.1 | HIMS-FAC-008 | Bed board: every ward's beds and their status on one screen (no patients yet) | ✅ done | Ready for Phase 3 admissions |
| 10 | 4.12 | HIMS-FAC-009 | Equipment register (what, where, status, service dates) | ✅ done (group 1) | Only the register; workflows wait for PO |
| 11 | 4.1 | HIMS-ORG-006 | Hospital logo and letterhead for printouts and emails | ✅ done (group 1) | Needed by Phase 2 visit summaries |
| 12 | 4.23 | HIMS-NOTIF-003 | Hospital-editable message templates (patient opt-out comes with Phase 2: HIMS-NOTIF-004) | ✅ done (group 1) | Before patient emails in slice 2B |
| 13 | 28.6 | HIMS-DATA-002 | Index check with production-like synthetic volume | ✅ done (group 6) | Before real volume |
| 14 | 19.2 | HIMS-QA-003 | Browser tests for the US deployment and the admin console | ✅ done (group 6) | US is a separate deployment |
| 15 | 13.1 | HIMS-IAM-014 | Passkeys as a second factor | ✅ done (group 4) | Optional upgrade over authenticator codes |
| 16 | 25, 29 | HIMS-DOC-001 | Requirement records and per-endpoint contract docs for built features | ✅ done (group 7) | Traceability (spec 25.3, 29) |
| 17 | 18 | HIMS-OPS-017 | Response-time targets (SLOs) measured locally | ✅ done (group 6) | Baseline before hosting |
| 18 | 4.22, 13.3 | HIMS-SEC-013 | Virus scanning of uploaded documents | ✅ done (group 3) | Before patient documents |
| 19 | 13.3, 18 | HIMS-SEC-020 | Filter the error text kept in traces with the same rules as logs | ✅ done (group 3) | Gap found by HIMS-SEC-019; needed before traces are sent anywhere (HIMS-PLAT-019) |
| 19a | 4.3 | HIMS-STAFF-016 | Clinical privileges: what each doctor may perform (the hospital keeps the list) | ✅ done (group 2) | Unblocked 2026-11-08 (CLIN: fine for now) |
| 19b | 4.3 | HIMS-STAFF-015 | Minimum staffing per shift, gap alerts (the hospital sets the numbers) | ✅ done (group 2) | Unblocked 2026-11-08 (CLIN) |
| 19c | 4.3 | HIMS-STAFF-013 | Leave balances and entitlements (the hospital sets them) | ✅ done (group 2) | Unblocked 2026-11-08 (PO) |
| 19d | 4.25, 28 | HIMS-COMP-006 | Retention purge with legal hold (the hospital sets the periods; nothing deleted until set) | ✅ done (group 5) | Unblocked 2026-11-08 (LEGAL) |
| 19e | 13 | HIMS-SEC-011 | Security review of the threat model | ✅ done | PO: when the whole of Phase 1 is complete; seven findings, five fixed ([security review](../compliance/security-review.md)) |
| — | 4.4 | HIMS-IAM-019 | Self-service cover requests | ⬜ optional | When hospitals ask |
| — | 4.3 | HIMS-STAFF-014 | Shift swaps requested by staff, approved by the head | ⬜ optional | When hospitals ask |
| — | 4.25 | HIMS-SEC-017 | Integrity check as a background job | ⬜ later | When the audit log nears ~1 million records |
| — | 19.2 | HIMS-QA-002 | Make browser tests a required check | ⬜ PO | You, in the GitHub branch rules |
| 19f | 7.2, 7.4, 13 | HIMS-IAM-021 | Supplier support access, the "locked box": ask, hospital approves, emergency opens at once (hospital not emailed), ends by itself, every request audited | ✅ done (group 9) | PO request 2026-11-12 ([support access](../workflows/support-access.md)) |
| 19g | 19, 31.1 | HIMS-QA-004 | Ten demo hospitals (5 India, 5 US, 3 branches each, own database each) with synthetic data for everything built | ✅ done (group 9) | PO request 2026-11-12 ([demo hospitals](../testing/demo-hospitals.md)); every later ticket adds its demo records |

### 4b. Phase 1: not buildable now (hosting stage at the end, deferred, moved, or unblocked on 2026-11-08)

| Spec § | Ticket | Task | Blocked by |
|---|---|---|---|
| 17, 30, 34 | HIMS-OPS-020 | Hosting analysis | ✅ done 2026-11-11 ([analysis](../architecture/hosting/hosting-analysis.md)) |
| 17, 31, 33 | HIMS-OPS-024 | The first free Development environment (no payment card): Render + Neon + cron-job.org, deploy from `development` ([guide](../workflows/render-neon-hosting.md)) | 🟡 in progress: code ready; the PO creates the service → ✅ done 2026-11-12: live, timer running, no "Must fix", hosting check in every pull request |
| 7.2 | HIMS-OPS-025 | Owner console (control plane): every hospital in one list (country, version, health, audit integrity), a link to each one's Support access page, no patient data (gap found in HIMS-IAM-021) | Hosting stage (needs the hospitals online) |
| 17, 30 | HIMS-OPS-003 | Terraform modules (network, ECS, RDS, Redis, S3, KMS, secrets, monitoring) | AWS |
| 17.2, 30.5 | HIMS-OPS-019 | Database activity logging (pgaudit) for owner and break-glass sessions; alarm when break-glass signs in (gap found in HIMS-OPS-007) | AWS |
| 17, 18 | HIMS-OPS-004 | Alarms and runbooks (errors, latency, database, queues, outbox) | AWS |
| 33 | HIMS-OPS-005 | Deploy pipeline with build once, promote to QA, Staging, Production | AWS / hosting |
| 33 | HIMS-OPS-006 | Migration release job with a lock; schema version per hospital | AWS / hosting |
| 7 | HIMS-OPS-008 | Hospital provisioning automation (control plane) | AWS |
| 4.23 | HIMS-OPS-011 | Real email provider per hosted environment | AWS / hosting |
| 4.22 | HIMS-OPS-015 | S3 document storage (KMS, versioning) | AWS |
| 13.4 | HIMS-SEC-016 | Copy the audit chain head to write-once storage | AWS |
| 4.25, 13.4 | HIMS-COMP-007 | Archive the audit log outside the database (with an "archived up to link N" marker), then purge it by its period (gap found in HIMS-COMP-006) | AWS / hosting |
| 17.3, 27.1 | HIMS-OPS-018 | Restore drill of a cloud snapshot with the same checks (gap found in HIMS-OPS-009) | AWS |
| 13.3 | HIMS-SEC-018 | Send the screens' protection headers at hosting | ✅ done 2026-11-11: the server sends them when it serves the screens (HIMS-OPS-022) |
| 18 | HIMS-PLAT-019 | Send traces to AWS | AWS |
| 18 | HIMS-OPS-021 | Load test with many people at once against the hosted test environment before go-live (gap found in HIMS-OPS-017) | AWS / hosting |
| 4.23 | HIMS-NOTIF-002 | SMS gateway (India DLT, US provider) | Deferred: SMS printed to the console for now (PO 2026-11-08) |
| 4.4, 36 | HIMS-IAM-008 | Single sign-on (OIDC/SAML) | Deferred: not now (PO 2026-11-08) |
| 4.4 | HIMS-IAM-018 | Clinical delegation | Moves to Phase 2 (needs clinical actions) |
| 4.3 | HIMS-STAFF-016 | Clinical privileges (what a doctor may perform) | ✅ unblocked 2026-11-08: step 19a |
| 4.3 | HIMS-STAFF-013 | Leave balances and entitlements | ✅ unblocked 2026-11-08: step 19c |
| 4.3 | HIMS-STAFF-015 | Minimum staffing per shift, gap alerts | ✅ unblocked 2026-11-08: step 19b |
| 3 | — | Approve the RBAC document, clinical role permissions | ✅ approved for now 2026-11-08 |
| 4.25 | HIMS-COMP-006 | Retention purge with legal hold | ✅ unblocked 2026-11-08: step 19d, built (group 5) |
| 23 | HIMS-COMP-001…005 | Counsel and hospital review of the compliance pack | ✅ approved for now 2026-11-08 |
| 23 | HIMS-SEC-011 | Security reviewer for the threat model | ✅ done 2026-11-11 (internal review, step 19e) |
| 13, 23 | HIMS-SEC-021 | Independent security review and penetration test of the hosted system, before real patient data (gap found in HIMS-SEC-011) | Hosting stage |
| 4.1 | — | Tax rules | Moves to Phase 5 (billing) |

### 4c. Phase 2 onwards

| Step | Phase | Spec § | Tickets | Task | Status | Blocked by |
|---|---|---|---|---|---|---|
| 19 | 2 | 26 | HIMS-PAT-000 | Sign off the Phase 2 P0 design (26 decisions) | ✅ approved for now 2026-11-08 | — (may be revisited) |
| 20 | 2 | 4.5, 13 | HIMS-PAT-001, 002, 005, 006; HIMS-IAM-010; HIMS-DATA-003 | Slice 2A: registration with MRN, search, chart header, restricted records, patient scope | ⬜ **next** (2026-11-12; first HIMS-PAT-001, which also registers the demo hospitals' invented patients) | Step 19 (done) → 🟡 **2026-11-12: HIMS-PAT-001 ✅ done** (registration with MRN, contacts, people, ID numbers, consents; demo patients registered); **next HIMS-PAT-002** (search), then PAT-005, PAT-006, HIMS-IAM-010, HIMS-DATA-003 · **2026-11-13: HIMS-PAT-002 ✅ done** (search); **next HIMS-PAT-005** (chart header), then PAT-006, HIMS-IAM-010, HIMS-DATA-003 · **2026-11-14: HIMS-PAT-005 ✅ done** (chart header and overview, record history for medical records); **next HIMS-PAT-006** (restricted records, emergency access), then HIMS-IAM-010, HIMS-DATA-003 · **2026-11-14, later: HIMS-PAT-006 ✅ done** (restricted records, emergency access with review); HIMS-IAM-010 moves to step 22 (it needs visits, HIMS-CLIN-001); **next HIMS-DATA-003** (Artifact A for patients/MPI), which closes step 20 · **2026-11-14, latest: HIMS-DATA-003 ✅ done; step 20 ✅ complete** (HIMS-PAT-007, 008, 009 and HIMS-IAM-023 wait in the backlog for their slices); **next step 21, HIMS-OPD-001** |
| 21 | 2 | 4.6, 4.23 | HIMS-OPD-001…004 | Slice 2B: schedules (uses step 1 rotas), appointments without double booking, walk-ins, queue, reminders | ⬜ · **2026-11-15: 🟡 HIMS-OPD-001 ✅ done** (doctor schedules; approved rota leave takes sessions off); **next HIMS-OPD-002** · **2026-11-15, later: HIMS-OPD-002 ✅ done** (appointments without double booking, move, cancel, To move list); **next HIMS-OPD-003** · **2026-11-15, latest: HIMS-OPD-003 ✅ done** (check-in with tokens, walk-ins, the OPD queue, the no-show job); **next HIMS-OPD-004** | Step 20 |
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
| 41 | 6 | 17, 27, 30 | HIMS-OPS-020 (done), HIMS-OPS-022/023/024, then the Phase 1 hosting items | Hosting stage: free Development first (ADR-034), paid hosting before real data: backups, disaster recovery, alarms | 🟡 analysis done; free Development live 2026-11-12 (HIMS-OPS-022, -023, -024 done) | At the very end (PO 2026-11-08) |
| 42 | 6 | 18, 19, 27 | — | Performance, security and recovery tests; clinical validation | ⬜ | Hosting, CLIN |
| 43 | 6 | 20, 35 | — | Hospital acceptance testing, training, controlled rollout | ⬜ | Everything above |

**Cross-cutting, at any time:** close the 19 decisions in section 36 (owner per row), review
ADR-009 to ADR-027 (accepted for now on 2026-11-08), and work through the 45-item readiness checklist (section 23).

## 5. Functional domains (section 4)

| § | Domain | Phase | Status | Left (🔓 now / 🔒 blocked) |
|---|---|---|---|---|
| 4.1 | Hospital and branches | 1 | 🟡 97% | logo and letterhead done (HIMS-ORG-006) · 🔒 tax rules (LEGAL) |
| 4.2 | Departments | 1 | 🟡 85% | 🔒 pricing, slots, escalation (CLIN) |
| 4.3 | Staff and credentials | 1 | ✅ 100% | ✅ shifts, leave, on-call, clinical privileges, leave balances, minimum staffing · optional: shift swaps · enforcing privileges with clinical actions (Phase 2) |
| 4.4 | Identity and access | 1 | 🟡 99% (department-level staff view done; supplier support access done 2026-11-12, HIMS-IAM-021) | 🔒 SSO (PO), break-glass (Phase 2) |
| 4.5 | Patient registration and MPI | 2 | ⬜ designed | 🔒 sign-off · **2026-11-12: 🟡 registration with MRN done (HIMS-PAT-001)**; next search (PAT-002) · **2026-11-13: search done (HIMS-PAT-002)**; next chart header (PAT-005) · **2026-11-14: chart header and overview done (HIMS-PAT-005)**; next restricted records (PAT-006) · **2026-11-14, later: restricted records and emergency access done (HIMS-PAT-006)**; next HIMS-DATA-003 · **2026-11-14, latest: Artifact A for patients/MPI accepted (HIMS-DATA-003)**; slice 2A complete; duplicates and merge (PAT-003, 004) and death (PAT-007) follow in slice 2D |
| 4.6 | Appointments and OPD | 2 | ⬜ designed · **2026-11-15: 🟡 doctor schedules done (HIMS-OPD-001)** · **later: appointments (HIMS-OPD-002)** · **latest: walk-ins, tokens, OPD queue, no-shows (HIMS-OPD-003)** | 🔒 sign-off (approved for now 2026-11-08); next appointments (HIMS-OPD-002) · next email reminders (HIMS-OPD-004) |
| 4.7 | Encounters and admissions | 2, 3 | ⬜ outpatient part designed | 🔒 sign-off; Phase 3 P0 |
| 4.8 | EHR/EMR | 2 | ⬜ | 🔒 CLIN |
| 4.9 | Nursing | 3 | ⬜ | 🔒 CLIN |
| 4.10 | Beds and wards | 1, 3 | 🟡 50% | bed board done (HIMS-FAC-008) · 🔒 allocation (Phase 3) |
| 4.11 | Diet and kitchen | 3 | ⬜ | 🔒 CLIN |
| 4.12 | Housekeeping, equipment, transport | 1, 3 | 🟡 20% | equipment register done (HIMS-FAC-009) · 🔒 requests, job orders, transport, service-due reminders (PO) |
| 4.13 | Pharmacy | 4 | ⬜ | 🔒 CLIN, VENDOR |
| 4.14 | eMAR | 4 | ⬜ | 🔒 CLIN |
| 4.15 | Laboratory | 4 | ⬜ | 🔒 CLIN, VENDOR |
| 4.16 | Radiology | 4 | ⬜ | 🔒 CLIN, VENDOR |
| 4.17 | Surgery, anaesthesia, ICU | 4 | ⬜ | 🔒 CLIN |
| 4.18 | Insurance and payers | 5 | ⬜ | 🔒 PAYER |
| 4.19 | Billing and revenue cycle | 5 | ⬜ | 🔒 LEGAL, PAYER |
| 4.20 | Procurement, inventory, accounting | 4, 5 | ⬜ | 🔒 PO (finance rules) |
| 4.21 | Patient portal | 6 | ⬜ | 🔒 needs 4.5+ |
| 4.22 | Documents and consent | 1, 2 | 🟡 30% | virus scanning done (HIMS-SEC-013) · 🔒 S3 (AWS), ClamAV at hosting, consent forms (LEGAL) |
| 4.23 | Notifications | 1, 2 | 🟡 70% | editable wording done (HIMS-NOTIF-003) · per-patient opt-out with Phase 2 (HIMS-NOTIF-004) · 🔒 SMS (VENDOR) |
| 4.24 | Reporting | 2–6 | ⬜ | 🔒 needs domains |
| 4.25 | Audit and governance | 1 | 🟡 95% | retention periods and legal holds done (HIMS-COMP-006; periods set by the hospital, LEGAL approved for now) · 🔒 write-once copy and audit log archive (AWS, HIMS-SEC-016, HIMS-COMP-007) |

## 6. Done so far

**2026-11-12:** 102 Phase 1 items done or approved (count corrected; see section 1): PR #1–#54, the
compliance pack and approvals, and group 9 (HIMS-IAM-021, HIMS-QA-004).

**2026-11-12, later:** 103: group 9 merged as PR #55, and HIMS-OPS-024 done (the free Development
environment live on Render + Neon; hosting check with the hosted settings in every pull request).

99 Phase 1 items: tickets delivered in PR #1–#50 (and #30) and the security review PR, plus the two approvals of 2026-11-08. The full list with what each PR did is in the
tracker's [PR history](spec-status.md#pr-history-traceability-spec-253) and
[work queue](spec-status.md#next-work-queue-dependency-free-in-recommended-order).

New tickets named here for the first time (HIMS-SEC-019, HIMS-FAC-008, HIMS-FAC-009,
HIMS-ORG-006, HIMS-DOC-001, HIMS-OPS-017, and HIMS-SEC-020, HIMS-OPS-018, HIMS-OPS-019, HIMS-OPS-020 and HIMS-STAFF-016 added
on 2026-11-08) are also in the Phase 1 backlog.

**2026-11-12, Phase 2:** HIMS-PAT-001 done: patient registration with MRN, contacts, people, ID numbers (encrypted, masked) and consents, with screens, the admin console section, the Receptionist and Medical records roles and the demo hospitals' invented patients. Phase 1 stays at 103 of 129. Next: HIMS-PAT-002.

**2026-11-13, Phase 2:** HIMS-PAT-002 done: patient search on the Patients screen and in the admin console (MRN or only its number, phone, ID number by fingerprint, names by similar spelling and by sound in any order with earlier names, age and sex), at most 50 minimal results, every search audited ([ADR-037](../decisions/ADR-037-patient-search.md)). Next: HIMS-PAT-005.

**2026-11-14, Phase 2:** HIMS-PAT-005 done: the patient chart, with a header that stays in view on every tab (name, MRN, age and sex, "Allergies not asked yet", unknown and merged flags), alerts from the server (also in the admin console), and Overview, Demographics and History tabs; History, for the medical records officer only (`patients.history`), lists who opened and changed the record with field names only and is audited ([patient chart](../workflows/patient-chart.md); decisions log rows 26–28). Next: HIMS-PAT-006.

**2026-11-14, Phase 2, later:** HIMS-PAT-006 done: restricted (VIP/staff) records, hidden from patient search (the exact MRN shows only "Restricted record") and opened only by medical records or, in an emergency, by a doctor for 4 hours with a reason; medical records are emailed and someone other than the user reviews it; every restricted opening is listed ([restricted records](../workflows/restricted-records.md); decisions log rows 29–32). Next: HIMS-DATA-003.

**2026-11-14, Phase 2, latest:** HIMS-DATA-003 done: the patient / MPI domain reviewed against spec 28.8 and accepted ([review](../architecture/data-architecture/patients-mpi-review.md)): the volume check now holds 500,000 invented patients (5.9 million rows in all) and checks 15 patient queries and 10 patient screens plus 2 console lists; it found and fixed **seven problems**: no index for the newest-patients list (306 ms, screen 611 ms), the MRN number part read every MRN by pattern (400 ms), earlier MRNs and the previous-MRN hospitals read whole tables, the exact MRN look-up did not name the hospital (hidden by PostgreSQL 18's skip scan on the PC; CI and hosting run 17), the hospital's time zone was read once per row (61 queries for a name search, 107 for the console's emergency access list) and the console's patient and issued-number lists sorted or counted whole tables (1.1 s; 513 ms); a search's total is counted up to 1,000 ("more than 1,000"). Migrations `patients.0004` and `numbering.0002` (indexes built `CONCURRENTLY`). Every database rule on the patient tables is broken on purpose by `test_data_invariants.py` (11 tests; a new rule without a test fails). Performance screen groups results by area (Patients, Audit log, …); console page **Restricted record openings** (missed in HIMS-PAT-006's console); demo hospitals record an index check. Follow-ups: HIMS-PAT-009 (name search at 10× the register), HIMS-IAM-023 (reporting user and patient data), HIMS-DATA-004 (Artifact A for the later P0 domains). Next: HIMS-OPD-001.

**2026-11-15, Phase 2:** HIMS-OPD-001 done (slice 2B starts): **doctor schedules and exceptions** ([how-to](../workflows/doctor-schedules.md), [record](../requirements/outpatient.md), [data design and Artifact A review](../architecture/data-architecture/scheduling.md), [ADR-038](../decisions/ADR-038-opd-sessions-and-free-slots.md)): new app `apps/scheduling` (tables `doctor_schedules`, `schedule_exceptions`; migration `scheduling.0001`); screen **Doctor schedules**: one department's week with each doctor's OPD sessions and free slots; weekly sessions on several weekdays (slot 5–120 minutes, up to 20 extra bookings, D11), changed or ended (days and hours never edited); doctor away (all day or part), holiday (a department, or the whole facility with a facility grant), extra session, each answering with the sessions it takes off; **leave approved on the Leave page takes sessions off by itself** (the step 1 rotas; leave asked shows "Leave asked"); suspended doctors' sessions show off; a posting or employment that ends ends them; no overlap for one doctor in any department (service under a row lock and a database exclusion constraint). New permissions `appointments.view`, `schedules.manage`; new role **OPD scheduler**; the head of department, branch administrator and front desk (view only; never why a doctor is away) get them; doctors see their own sessions on My schedule. Admin console: Doctor schedules and Schedule exceptions with the same rules, plus **Leave balances** (missed from HIMS-STAFF-013's console). Feature **Appointments and outpatient visits** live per facility. Every database rule has a test (`test_schedule_invariants.py`); four queries and two screens in the volume check (area Outpatient (OPD)). Demo: sessions and every kind of exception per branch and an `opd.<branch>@` account; `add_demo_doctor_schedules` for the hosted hospital. Follow-ups: HIMS-OPD-002 notes (booked patients when sessions go off, slot changes under bookings, the Leave page's approval), new HIMS-OPD-005 (other clinicians' clinics, PO to decide). Decisions log rows 37–40. Next: HIMS-OPD-002.

**2026-11-15, Phase 2, later:** HIMS-OPD-002 done: appointments. The front desk and OPD schedulers book patients into doctors' free slots (or over the slots when a session allows it), move them (linked to the old appointment) and cancel them with the reason; the database refuses a second booking of a slot even at the same moment; when a doctor cannot come, the booked patients are listed under To move ([appointments](../workflows/appointments.md), [ADR-039](../decisions/ADR-039-appointments-no-double-booking.md)). Phase 2: 31 tickets, 6 done, 25 left. Next: HIMS-OPD-003 (walk-ins, tokens, the OPD queue).

**2026-11-15, Phase 2, latest:** HIMS-OPD-003 done: the day of the visit. On the **OPD queue** the front desk checks booked patients in (each gets the doctor's next token, in the order they arrive), checks in walk-ins without using a slot, calls the next token in to the doctor and marks the patient seen; patients not checked in by the end of their session are marked "did not come" by a job every 15 minutes ([OPD queue](../workflows/opd-queue.md), [ADR-040](../decisions/ADR-040-opd-queue-tokens-and-no-shows.md)). Phase 2: 32 tickets, 7 done, 25 left. Next: HIMS-OPD-004 (email confirmations and reminders).
