# Decisions and approvals log

Approvals and decisions from the product owner (PO), clinical governance (CLIN) and legal (LEGAL),
as relayed to engineering. The specification is not edited; where a decision differs from it, the
decision is recorded here and in an ADR. Every entry can be revisited: "approved for now" means
work may proceed on it, and a later change is handled as a normal change.

## 2026-11-08 (relayed by the PO)

**What was said:** "CLIN, LEGAL and PO have reviewed and told us that for now it is fine; later on,
if required, we can change it." SMS: print to the console for now, a gateway later. Security
review: when the whole of Phase 1 is complete. Hosting: not AWS; deploy at the very end on Oracle
Cloud's free offering, after an analysis of what that deployment needs.

| # | Item | Who | Decision | Effect |
|---|---|---|---|---|
| 1 | Roles and permissions document (incl. clinical roles' permissions), [RBAC](Hospital_Departments_and_Doctors_RBAC.MD) | CLIN, PO | **Approved for now** | Section 3 and 13.2 no longer wait for approval |
| 2 | Compliance pack: requirements, risks, incident procedure, notices ([compliance](../compliance/README.md); HIMS-COMP-001…005) | LEGAL | **Approved for now** | Counsel review no longer blocks; revisit before real patient data if required |
| 3 | Phase 2 P0 design and its 26 decisions D1–D26 ([Phase 2 P0](../p0/phase-2-patients/README.md)) | PO, CLIN, LEGAL | **Approved for now, as proposed.** D6, D7, D8 as already decided by the PO on 2026-10-30. D21 (an open question) as its first option: patient-reported current medicines only, prescriptions in Phase 4 | **Phase 2 can be built** (slices 2A–2D) |
| 4 | Architecture decisions ADR-009 to ADR-026 | PO | **Accepted for now** | Status stays "Proposed" in each file until reviewed one by one; no work waits on them |
| 5 | Clinical privileges (what a doctor may perform), minimum staffing per shift | CLIN | **Fine for now:** build them with values the hospital sets itself | Become buildable (HIMS-STAFF-016, HIMS-STAFF-015) |
| 6 | Leave balances and entitlements | PO | **Fine for now:** build with entitlements the hospital sets itself | Becomes buildable (HIMS-STAFF-013) |
| 7 | Retention periods and legal hold | LEGAL | **Fine for now:** build the purge with periods the hospital sets (nothing deleted until a period is set) | Becomes buildable (HIMS-COMP-006); **built 2026-11-10** (nothing deleted until the hospital sets a period; [ADR-030](../decisions/ADR-030-retention-purge-and-legal-hold.md)) |
| 8 | Single sign-on (OIDC/SAML) | PO | **Not now**; passwords with two-factor are fine | HIMS-IAM-008 deferred (optional) |
| 9 | SMS gateway | PO | **Print to the console for now** (as today); a gateway later | HIMS-NOTIF-002 deferred |
| 10 | Security review of the threat model | PO | **When the whole of Phase 1 is complete** | HIMS-SEC-011 becomes the last Phase 1 step; done 2026-11-11 as an internal review ([security review](../compliance/security-review.md)); the independent review and penetration test is HIMS-SEC-021 (hosting stage) |
| 11 | Hosting | PO | **Oracle Cloud (free offering) instead of AWS, at the very end**, after an analysis ([ADR-027](../decisions/ADR-027-hosting-on-oracle-cloud.md)) | AWS-labelled items become the "hosting stage"; first step is the analysis (HIMS-OPS-020) |
| 12 | Clinical delegation (HIMS-IAM-018), tax rules | CLIN, LEGAL | Belong with the clinical actions (Phase 2) and billing (Phase 5) | Moved to those phases |

Names of the approvers are to be filled in on the sign-off tables when given; they are not
guessed here.

## 2026-11-12 (the PO)

| # | Decision | Who | Answer | What it changes |
|---|---|---|---|---|
| 13 | How the software supplier gets into a hospital's system | PO | **The "locked box"**: the supplier asks with a reason, the hospital's administrator approves; in an emergency the supplier opens it at once and **the hospital is not told** (no email); it ends by itself after a few hours (2 by default); every request the supplier makes is recorded in the hospital's audit log, which nobody can change ("fine, can change later") | Built as HIMS-IAM-021 ([ADR-035](../decisions/ADR-035-supplier-support-access.md)). Emergency access still shows on the hospital's Support access page and audit log; the email can be switched on later (`HIMS_SUPPORT_EMERGENCY_NOTICE`). **LEGAL to review before real patient data** (spec 7.2 says the supplier "should not silently gain access"; contracts may require notice) |
| 14 | Demo data | PO | 5 Indian and 5 US hospitals, 3 branches each, demo data for everything built and for later phases | Built as HIMS-QA-004 ([demo hospitals](../testing/demo-hospitals.md)); patients are invented now and registered with HIMS-PAT-001; every later ticket adds its demo records |
| 15 | One hospital must never see another; each hospital its own admin console | PO | Confirmed as already built: each hospital is its own deployment and database (ADR-003, ADR-009); the "choose a hospital" page is the developer launcher on the PO's PC only. A list of all hospitals for the supplier is the owner console (HIMS-OPS-025, hosting stage) | Launcher page now says so; HIMS-OPS-025 added |
| 16 | Approvals, SMS, security review, AWS | PO, CLIN, LEGAL | Repeated: CLIN, LEGAL and PO approvals of 2026-11-08 stand "for now"; SMS stays on the console; the security review after all of Phase 1; AWS at the very end (the free Development environment runs on Render + Neon) | No change |
| 17 | The free Development environment, and the Neon password | PO | HIMS-OPS-024 closed: the hosted Development (Render + Neon + cron-job.org) is fine for now; the Neon database password reset is done later by the PO; AWS / paid hosting stays at the very end | Tracker, roadmap and backlog mark HIMS-OPS-024 Done; the reset stays in the [guide](../workflows/render-neon-hosting.md), step 1.3 |
| 18 | Phase 2 can start | PO | Asked whether, leaving AWS aside, Phase 1 is complete: yes for the application part; the 26 items left are the hosting stage at the end, 4 optional items, 2 PO deferrals and 5 items moved to Phase 2, none blocking Phase 2 | Next: Phase 2, Slice 2A, HIMS-PAT-001 ([roadmap](roadmap.md) section 4c) |
