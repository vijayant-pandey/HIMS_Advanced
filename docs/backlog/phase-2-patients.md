# Backlog: Phase 2, patients and outpatient care

Design: [Phase 2 P0 draft](../p0/phase-2-patients/README.md). **No ticket starts before PO and
doctor sign-off** (spec 26). Legal items must close before real patient data.

## EPIC HIMS-PAT: Patients (slice 2A, 2D)

| ID | Ticket | Status |
|---|---|---|
| HIMS-PAT-000 | P0 design sign-off (PO + reviewing doctor; legal items D6, D7, D9, D18, D24) | Waiting for sign-off |
| HIMS-PAT-001 | Patient registration with MRN, contacts, relationships, identifiers (encrypted/masked), consents | To do |
| HIMS-PAT-002 | Patient search (MRN, phone, ID, similar name) with minimal results; chart read auditing | To do |
| HIMS-PAT-003 | Duplicate detection at registration and possible-duplicates list | To do |
| HIMS-PAT-004 | Two-person merge with 30-day undo | To do |
| HIMS-PAT-005 | Patient chart header and overview | To do |
| HIMS-PAT-006 | Restricted (VIP/staff) records and emergency access with review | To do |

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
