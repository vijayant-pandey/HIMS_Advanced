# Data retention schedule (spec 13.3, 13.4, 23, 28.1 #5; HIMS-COMP-004)

DRAFT. **Today HIMS deletes almost nothing** (the only technical deletions are listed below), which is
the safe default. Counsel fills the "Period" column per country before go-live, because keeping data too
long is itself a risk under DPDP (section 8(7)). Numbers below marked *confirm* are starting points, not
advice; sources conflict for Indian medical records.

| Records | Where | India: period | US: period | Why |
|---|---|---|---|---|
| Patient clinical records (Phase 2) | patients, clinical tables | Counsel to set: medical council rules, often cited as 3 years from last contact, many hospitals keep longer; medico-legal cases longer (*confirm*) | Counsel to set: state law, commonly 6 to 10 years; minors longer (*confirm*) | Care, law, claims |
| Audit log, tamper chain | audit tables | At least 1 year (DPDP Rules), 180 days (CERT-In) as minimums; proposal: same as clinical records | At least 6 years for HIPAA documentation (*confirm*); proposal: same as clinical records | Evidence |
| System logs | hosting | 180 days in India (CERT-In), 1 year (DPDP); proposal 1 year | Proposal 1 year | Investigation |
| Security incidents, notices | security_incidents… | Proposal 6 years | At least 6 years (*confirm*) | Proof of response |
| Risks, requirements, reviews, policies | compliance, access_reviews | Proposal 6 years | At least 6 years (*confirm*) | Proof of governance |
| Staff records, licences, documents | staff tables | Counsel to set: employment law | Counsel to set | Employment, credentialing |
| Sign-in register | user_sessions | Proposal 1 year after the account ends | Proposal 6 years (*confirm*) | Accountability |
| Message log | notifications | Proposal 1 year | Proposal 1 year | Proof of delivery |
| Consents and notices (Phase 2) | patient_consents | With the patient record | With the patient record | Proof of consent |

## What HIMS deletes today

Expired idempotency records (48 hours) · expired browser sessions · two-factor devices and backup codes on
reset (audited) · department opening-hour rows when replaced (audited). Secret-bearing copies of messages are
erased once delivered.

## Legal hold (to build when the periods are set; built 2026-11-10, HIMS-COMP-006)

When a dispute or investigation is expected, counsel issues a hold and affected records must not be purged
even if their period has passed. Any purge job built later (HIMS-COMP-006) must check for holds first,
record what it removed, and never break the audit chain (an "archived up to link N" marker is required; see
[audit-integrity.md](../architecture/data-architecture/audit-integrity.md)).

**Built (2026-11-10, HIMS-COMP-006):** the hospital sets periods for six kinds of housekeeping record (sign-in register, message log, invitations, password resets, browser block reports, reviewed console refusals) on Compliance → Retention. Nothing is deleted until a period is set; a first or shorter period waits 7 days; legal holds (whole kinds or one person) always win; each daily run is recorded. The rows in the table above that are not among those six (clinical, audit, incidents, governance, staff, consents) are **not** purged by it. The audit log needs the archive marker first (HIMS-COMP-007, hosting stage). How-to: [retention-purge.md](../workflows/retention-purge.md).

## Person's right to erasure (India)

DPDP gives a right to erasure unless another law requires keeping the data. Medical record laws usually do,
so requests are checked by medical records and counsel, answered, and logged. Process to be built with Phase 2
(`DPDP-RIGHTS`).
