# Backlog: Phase 2, patients and outpatient care

Design: [Phase 2 P0 draft](../p0/phase-2-patients/README.md). **No ticket starts before PO and
doctor sign-off** (spec 26). Legal items must close before real patient data.

**2026-11-08:** PO, CLIN and LEGAL approved the P0 design **for now** ([decisions log](../status/decisions-log.md),
row 3), so Phase 2 can be built. **2026-11-12:** every ticket also adds its records to the demo
hospitals (`backend/apps/demo/seed.py`; [demo hospitals](../testing/demo-hospitals.md), HIMS-QA-004).

## EPIC HIMS-PAT: Patients (slice 2A, 2D)

| ID | Ticket | Status |
|---|---|---|
| HIMS-PAT-000 | P0 design sign-off (PO + reviewing doctor; legal items D6, D7, D9, D18, D24) | Waiting for sign-off → approved for now 2026-11-08 (decisions log row 3) |
| HIMS-PAT-001 | Patient registration with MRN, contacts, relationships, identifiers (encrypted/masked), consents | Done 2026-11-12 (screens Patients, Register new patient and the patient record; admin console; roles Receptionist / front desk and Medical records officer; ID numbers encrypted, masked and refused on a second patient; reading audited; the demo hospitals' invented patients registered) · earlier: To do (also registers the invented demo patients, `apps/demo/patients.py`) |
| HIMS-PAT-002 | Patient search (MRN, phone, ID, similar name) with minimal results; chart read auditing | Done 2026-11-13 (one search box on Patients and in the admin console: MRN or only its number, phone, ID number by fingerprint, names by similar spelling and by sound in any order with earlier names, age and sex filters; at most 50, best first; every search audited without its words; trigram and sound-key indexes, [ADR-037](../decisions/ADR-037-patient-search.md); demo: one earlier family name per branch and printed example searches; the hosted Development hospital can get the demo records) · earlier: To do |
| HIMS-PAT-003 | Duplicate detection at registration and possible-duplicates list | To do (also: a possible duplicate that is a restricted record must be shown to the front desk without its details, e.g. "a restricted record may match: ask medical records"; from HIMS-PAT-006) |
| HIMS-PAT-004 | Two-person merge with 30-day undo | To do |
| HIMS-PAT-005 | Patient chart header and overview | Done 2026-11-14 (the chart: a header that stays in view on every tab with name, MRN, age and sex, "Allergies not asked yet", unknown and merged flags; alerts worked out by the server, also in the admin console; tabs Overview, Demographics and History; History, for medical records only (new permission `patients.history`), lists who opened and changed the record, field names only, and is audited; demo: per branch a child without a guardian and an adult without the privacy notice; [how-to](../workflows/patient-chart.md)) · earlier: To do |
| HIMS-PAT-006 | Restricted (VIP/staff) records and emergency access with review | Done 2026-11-14 (medical records restrict a record (VIP, staff, other) with a reason; hidden from search in the app and the console for people without `patients.restricted`, an exact MRN shows "Restricted record" only; every action on it refused (`RESTRICTED_RECORD`) unless the permission or emergency access; emergency access (`clinical.emergency_access`, the head of department today): 4 hours, reason, emailed to medical records without patient details, ended early on request; review by someone else from medical records (`patients.records_correct`) once ended; restricted record openings listed; header chip and alert; screens Restricted record, Emergency access; console section and Emergency access list; demo: one restricted record per branch and two emergency accesses, `add_demo_restricted_records` for the hosted hospital; [how-to](../workflows/restricted-records.md)) · earlier: To do (also: hide restricted records from patient search, in the app and the console search, for people without `patients.restricted`; from HIMS-PAT-002) (also: the **Restricted** flag in the chart header and an alert, from HIMS-PAT-005) |
| HIMS-PAT-008 | Weekly email to medical records: emergency access waiting for review and the week's restricted record openings (D14 "reviewed weekly"; gap found in HIMS-PAT-006, which emails each use at once and keeps the review list) | To do |
| HIMS-PAT-007 | Record a patient's death (date and time, by a doctor); the record becomes read-only except medical-records corrections (P0 part 01 §1; gap found in HIMS-PAT-001) | To do (also: the **Deceased** flag in the chart header, from HIMS-PAT-005) |

## EPIC HIMS-OPD: Scheduling and outpatient department (slice 2B)

| ID | Ticket | Status |
|---|---|---|
| HIMS-OPD-001 | Doctor schedules and exceptions | To do |
| HIMS-OPD-002 | Appointments without double booking (exclusion constraint), reschedule, cancel | To do (also: the Overview's "Next appointment" line and a Book button in the chart header, from HIMS-PAT-005) |
| HIMS-OPD-003 | Walk-ins, tokens and OPD queue; no-show job | To do |
| HIMS-OPD-004 | Email confirmations and reminders (needs notification service) | To do |

## EPIC HIMS-CLIN: Visit and clinical recording (slice 2C)

| ID | Ticket | Status |
|---|---|---|
| HIMS-CLIN-001 | Outpatient encounter lifecycle with visit numbers | To do (also: add the last visit date and department to the patient search results, P0 part 01 §2; gap found in HIMS-PAT-002) (also: the chart's **Visits** tab, a timeline, and the clinical part of the chart only for staff in scope, P0 part 04 D13; from HIMS-PAT-005) (also: emergency access, built for restricted records in HIMS-PAT-006, must also open the clinical part of an out-of-scope chart (D13), and the Doctor and OPD nurse roles get `clinical.emergency_access`; the browser test then covers a doctor's emergency access and a second medical records officer's review; from HIMS-PAT-006) |
| HIMS-CLIN-002 | Vitals with plausibility and abnormal flags (LOINC/UCUM) | To do (also: the chart's **Vitals** tab and the Overview's "Last vitals" line, from HIMS-PAT-005) |
| HIMS-CLIN-003 | Allergies incl. explicit "no known allergies" | To do (also: fill the chart header's `allergy_status` (today always `not_asked`) with "No known allergies" or the active allergies in red, and the Overview's Allergies line; decide with the doctor whether the front desk sees them; from HIMS-PAT-005) |
| HIMS-CLIN-004 | ICD-10 / ICD-10-CM catalogue import and coded diagnoses | To do (also: the Overview's "Problems (diagnoses)" line, from HIMS-PAT-005) |
| HIMS-CLIN-005 | Consultation notes: draft, sign, amend, addendum, entered in error | To do (also: the chart's **Notes** tab, from HIMS-PAT-005) |
| HIMS-CLIN-006 | Patient-reported current medicines (D21) | To do (also: the Overview's "Medicines (as reported)" line, from HIMS-PAT-005) |
| HIMS-CLIN-007 | Consultation screen and "my patients today" | To do |

## EPIC HIMS-RPT: Reports (slice 2D)

| ID | Ticket | Status |
|---|---|---|
| HIMS-RPT-001 | Visit summary print/PDF | To do |
| HIMS-RPT-002 | OPD daily list; unsigned-notes report | To do |

## EPIC HIMS-NOTIF: Notifications for patients

| ID | Ticket | Status |
|---|---|---|
| HIMS-NOTIF-004 | Per-patient opt-out of messages, with consent (spec 4.23; split from HIMS-NOTIF-003 because it needs patients) | To do |

## EPIC HIMS-STAFF: Privileges in clinical work

| ID | Ticket | Status |
|---|---|---|
| HIMS-STAFF-017 | Check clinical privileges in clinical actions with `holds_privilege`, and remind HR before a privilege's review date (spec 4.3; gap found in HIMS-STAFF-016, which keeps the record) | To do |

## EPIC HIMS-IAM: Access to patient records

| ID | Ticket | Status |
|---|---|---|
| HIMS-IAM-022 | Supplier support and patient records: today the supplier's support account never holds patient permissions, even with a lent administrator role (spec 7.2). If the PO wants support to see patients in some cases, add a separate, hospital-approved "include patient records" choice that the hospital is always told about (gap found in HIMS-PAT-001; decisions log row 20) | To do (PO to decide) |
