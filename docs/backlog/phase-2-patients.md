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
| HIMS-PAT-002 | Patient search (MRN, phone, ID, similar name) with minimal results; chart read auditing | To do |
| HIMS-PAT-003 | Duplicate detection at registration and possible-duplicates list | To do |
| HIMS-PAT-004 | Two-person merge with 30-day undo | To do |
| HIMS-PAT-005 | Patient chart header and overview | To do |
| HIMS-PAT-006 | Restricted (VIP/staff) records and emergency access with review | To do |
| HIMS-PAT-007 | Record a patient's death (date and time, by a doctor); the record becomes read-only except medical-records corrections (P0 part 01 §1; gap found in HIMS-PAT-001) | To do |

## EPIC HIMS-OPD: Scheduling and outpatient department (slice 2B)

| ID | Ticket | Status |
|---|---|---|
| HIMS-OPD-001 | Doctor schedules and exceptions | To do |
| HIMS-OPD-002 | Appointments without double booking (exclusion constraint), reschedule, cancel | To do |
| HIMS-OPD-003 | Walk-ins, tokens and OPD queue; no-show job | To do |
| HIMS-OPD-004 | Email confirmations and reminders (needs notification service) | To do |

## EPIC HIMS-CLIN: Visit and clinical recording (slice 2C)

| ID | Ticket | Status |
|---|---|---|
| HIMS-CLIN-001 | Outpatient encounter lifecycle with visit numbers | To do |
| HIMS-CLIN-002 | Vitals with plausibility and abnormal flags (LOINC/UCUM) | To do |
| HIMS-CLIN-003 | Allergies incl. explicit "no known allergies" | To do |
| HIMS-CLIN-004 | ICD-10 / ICD-10-CM catalogue import and coded diagnoses | To do |
| HIMS-CLIN-005 | Consultation notes: draft, sign, amend, addendum, entered in error | To do |
| HIMS-CLIN-006 | Patient-reported current medicines (D21) | To do |
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
