# India: DPDP, CERT-In, ABDM and Aadhaar assessment (HIMS-COMP-002, 003)

DRAFT for counsel. Requirement-by-requirement status is in
[requirements-matrix.md](requirements-matrix.md) and on the Compliance page.

## Who is what under DPDP

The **hospital** is the Data Fiduciary (decides why and how data is processed). The **HIMS provider** and
hosting, email and SMS vendors are Data Processors acting under contract. Patients and staff are Data
Principals. Counsel checks whether the hospital is a *Significant* Data Fiduciary, which brings more duties.

## When it applies

Rules notified November 2025, in stages: definitions and the Board at once; consent managers after one year;
most duties (notice, security, breach, retention, rights) **18 months after publication, around May 2027**.
CERT-In's directions already apply. Counsel confirms dates for each hospital.

## Assessment

| Duty | What HIMS provides | What the hospital must do | Status |
|---|---|---|---|
| Notice and consent (or a lawful use such as medical treatment) | Designed at registration (D9): notice given, consent recorded separately for SMS and email, withdrawal history | Write the notice in English and local languages; counsel confirms the legal basis | Phase 2 |
| Security safeguards (Rule 6) | Access control, encryption of secrets and ID numbers, masking, audit log, monitoring | Hosting safeguards, contracts | In progress |
| Logs for at least one year | Audit events never deleted | System logs at hosting | In progress |
| Breach notice (Rule 7) | Incident log, deadlines, alerts, runbook | Send the notices, run a drill | Built |
| Erase when no longer needed | [retention-schedule.md](retention-schedule.md) | Set periods with counsel | To do |
| Rights: access, correct, erase, grievance, nominate | Corrections audited; request process with Phase 2 | Name a contact, answer requests | To do |
| Children's data | Guardian recorded in Phase 2 | Counsel confirms healthcare exemptions and consent method | To do |
| Processors under contract | [vendors.md](vendors.md) | Sign contracts | To do |
| Publish a contact | Shown in the notice | Name the person | To do |

## CERT-In directions (28 April 2022)

Report listed cyber incidents **within 6 hours** of noticing (HIMS creates the deadline for every incident, and
counsel or the lead marks it "not required" if the type is not listed). Keep system logs for a **rolling 180
days within India** (at hosting). Synchronise clocks to a national time source (at hosting). Name a point of
contact with CERT-In (hospital).

## ABDM (only if the hospital joins)

ABHA numbers can be recorded as "not verified" (D8). Creating and verifying ABHA, linking records and consent-
based sharing need ABDM registration, sandbox testing and security certification, planned for Phase 6. Read the
current Health Data Management Policy and technical requirements before starting (spec 12.2).

## Aadhaar

**Decision D6 (product owner):** staff may enter the number for now; it will be stored encrypted, shown masked
and marked "not verified". **This must be settled before real patients.** UIDAI rules restrict storing full
Aadhaar numbers (an "Aadhaar Data Vault" applies to some entities) and collecting Aadhaar cannot normally be
made compulsory. Ask counsel; the safer fallback is storing only the last 4 digits. Tracked as
`AADHAAR-STORAGE`.

## Questions for counsel

1. Legal basis for treatment data: consent, or a "certain legitimate use" for medical treatment?
2. Is the hospital a Significant Data Fiduciary?
3. Does CERT-In's 6-hour rule apply to every hospital incident type we log?
4. Aadhaar: may we store the full number at all?
5. Retention periods for clinical, medico-legal and staff records, by state?
6. Do the SPDI Rules still apply until DPDP commences, and for which data?
7. Where must data, backups and logs physically stay?
