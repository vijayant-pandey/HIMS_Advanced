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
| 7 | Retention periods and legal hold | LEGAL | **Fine for now:** build the purge with periods the hospital sets (nothing deleted until a period is set) | Becomes buildable (HIMS-COMP-006) |
| 8 | Single sign-on (OIDC/SAML) | PO | **Not now**; passwords with two-factor are fine | HIMS-IAM-008 deferred (optional) |
| 9 | SMS gateway | PO | **Print to the console for now** (as today); a gateway later | HIMS-NOTIF-002 deferred |
| 10 | Security review of the threat model | PO | **When the whole of Phase 1 is complete** | HIMS-SEC-011 becomes the last Phase 1 step |
| 11 | Hosting | PO | **Oracle Cloud (free offering) instead of AWS, at the very end**, after an analysis ([ADR-027](../decisions/ADR-027-hosting-on-oracle-cloud.md)) | AWS-labelled items become the "hosting stage"; first step is the analysis (HIMS-OPS-020) |
| 12 | Clinical delegation (HIMS-IAM-018), tax rules | CLIN, LEGAL | Belong with the clinical actions (Phase 2) and billing (Phase 5) | Moved to those phases |

Names of the approvers are to be filled in on the sign-off tables when given; they are not
guessed here.
