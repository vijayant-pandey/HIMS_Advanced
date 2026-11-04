# HIPAA: Security Rule safeguards and risk analysis (US deployment; HIMS-COMP-001)

DRAFT. HHS expects a documented, organisation-wide risk analysis (45 CFR 164.308(a)(1)); this gives the
software part and a worksheet. Requirement-by-requirement status is in
[requirements-matrix.md](requirements-matrix.md) and on the Compliance page. HIPAA has no official
"certification": do not claim compliance because of this document (spec 12.3).

## Who is what

The **hospital** is the covered entity. The **HIMS provider** handling patient data for it is a business
associate and must sign a BAA, as must hosting, email and SMS vendors ([vendors.md](vendors.md)).

## Safeguards

| Safeguard | Who | Status |
|---|---|---|
| **Administrative** | | |
| Risk analysis and management | Hospital + HIMS | Worksheet below; register in the app |
| Security official | Hospital | To name; role exists in HIMS |
| Workforce access, termination | Both | Built: roles, reviews, access ended on leaving |
| Training | Hospital | To do |
| Incident procedures | Both | Built: log + runbook; drill to do |
| Contingency plan | Hospital + hosting | Later, with hosting |
| Evaluation | Hospital | To schedule yearly |
| Business associate contracts | Hospital | To sign |
| **Physical** | | |
| Facility, workstation, device and media controls | Hospital + hosting | To do |
| **Technical** | | |
| Unique user IDs, automatic logoff | HIMS | Built (30-minute idle sign-out) |
| Emergency access | HIMS | Designed for Phase 2 (D14) |
| Encryption at rest | HIMS + hosting | Secrets encrypted now; disks and backups at hosting |
| Audit controls | HIMS | Built: append-only, tamper-evident; chart reads in Phase 2 |
| Integrity | HIMS | Built for configuration; clinical amendments in Phase 2 |
| Authentication | HIMS | Built: two-factor for privileged roles |
| Transmission security | HIMS + hosting | Production forces HTTPS; TLS at hosting |

## Risk analysis worksheet (the hospital completes it yearly and after major changes)

1. **Scope:** list every system, device and vendor holding electronic patient data (not only HIMS).
2. **Data flows:** where it is created, stored, sent; add to [threat-model.md](threat-model.md).
3. **Threats and vulnerabilities:** start from the risk register; add site-specific ones (shared PCs, paper
   printouts, Wi-Fi, former staff).
4. **Current controls:** what is really in place, not planned.
5. **Likelihood and impact:** score 1 to 5 each in the register.
6. **Plan:** treatment, owner and date for every risk.
7. **Document and keep it:** keep the record for at least six years.

## Patient rights to build (Phase 2 and later)

Notice of Privacy Practices acknowledgment · access and copies · amendments · accounting of disclosures ·
minimum necessary. These are tracked as `HIPAA-PRIV-*`.
