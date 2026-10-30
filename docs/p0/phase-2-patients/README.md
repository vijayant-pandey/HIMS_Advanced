# Phase 2 P0 design: patients and outpatient care (DRAFT for sign-off)

**Status:** DRAFT 1, 2026-10-30. **Not approved.** Nothing in this pack is built until it is
signed off (spec 26: "do not build critical data models or clinical workflows on unreviewed
assumptions").

**Spec:** 4.5 (patient registration and MPI), 4.6 (appointments and OPD), 4.7 (encounters,
outpatient part), 9 (data model), 13 (privacy), 15.3 (patient chart), 20 Phase 2, 21 steps 5–7,
26 (P0-A to P0-I), 28 (data architecture).

**Phase 2 exit criterion (spec 20):** the hospital can manage patients and outpatient visits end
to end.

## How to review (for you and the doctor)

1. Read the **decisions** table below. Each row is a choice only you, a doctor or legal can make.
   Every row has a **proposal**. Write "OK" or your change in the last column.
2. Skim the parts that concern you:

| Part | For | What it holds |
|---|---|---|
| [01 Functional requirements](01-functional-requirements.md) | You + doctor | What each screen does, rules, error cases (P0-A) |
| [02 Database design](02-database-design.md) | Engineering (doctor: skim the clinical tables) | Every table and column (P0-B) |
| [03 State machines](03-state-machines.md) | Doctor + engineering | Allowed status changes for visits, notes, merges… (P0-C) |
| [04 Roles and permissions](04-roles-and-permissions.md) | You + doctor | Who may see and do what (P0-D) |
| [05 Country, privacy and terminology](05-country-privacy-terminology.md) | You + legal + doctor | India/US rules, consent, ID numbers, code systems (P0-G, P0-H) |
| [06 Screens, API and tests](06-screens-api-tests.md) | You + engineering | Screen sketches, endpoints, acceptance tests, build plan (P0-I) |

3. Sign the table at the end. Then I build Phase 2 in four slices (2A–2D, part 06).

## What Phase 2 includes, and what it does not

| Included | Not in Phase 2 (later phase) |
|---|---|
| Patient registration with MRN, contacts, guardian/next of kin, ID numbers | Admissions, beds for patients, transfers, discharge (Phase 3) |
| Patient search; duplicate warning; controlled merge (and undo) | Prescriptions / medication orders, pharmacy (Phase 4) |
| Doctor schedules, appointments, walk-ins, tokens/queue, check-in, no-show | Lab and radiology orders and results (Phase 4) |
| Outpatient visit (encounter) with visit number | Insurance eligibility, billing, consultation fees (Phase 5) |
| Vitals, allergies, diagnoses (coded), consultation notes (sign, amend) | Patient portal, ABDM/ABHA linking, FHIR exchange (Phase 6) |
| Patient chart (header with allergies, visit timeline) | SMS/WhatsApp reminders (needs a vendor; email reminders are in) |
| Basic reports: visit summary print, daily OPD list | Telemedicine video visits |

## Decisions needed

**Owner:** PO = you · DR = reviewing doctor · LEGAL = legal/compliance.

| # | Question | Proposal | Owner | Your answer |
|---|---|---|---|---|
| D1 | Who registers patients? | Front-desk **Receptionist** role; nurses and doctors may also register walk-ins | PO | |
| D2 | Required fields to register | Name (one name is enough), sex, date of birth **or** age, mobile phone **or** "no phone" tick; everything else optional | PO, DR | |
| D3 | Unknown/unconscious patients | Allowed: "Unknown male/female, approx. age", flagged; details completed later | DR | |
| D4 | Duplicate check | Warn on likely duplicates (same ID number; or similar name + same birth year; or same phone + similar name). Receptionist must pick the existing patient or confirm "different person" with a reason | PO | |
| D5 | Who merges duplicate records? | **Medical records officer** requests; a **second** officer or admin approves (two-person rule); undo possible within 30 days | PO, DR | |
| D6 | Aadhaar (India) | **Do not store** the full Aadhaar number; store only the last 4 digits as a reference (Aadhaar Act rules) | LEGAL | |
| D7 | SSN (US) | **Do not collect** SSN; optional last 4 digits only if a payer requires it later | LEGAL | |
| D8 | ABHA (India) | Phase 2: record ABHA number/address typed in (marked "not verified"). Verified ABHA creation/linking via ABDM is a separate project (needs ABDM registration) | PO | |
| D9 | Consent at registration (DPDP / HIPAA notice) | Record that the privacy notice was given and the patient agreed to data processing for care; record SMS/email consent separately | LEGAL | |
| D10 | Appointment model | Slots per doctor session (e.g. 10 minutes) **plus** token numbers per doctor per day; walk-ins get the next token | PO, DR | |
| D11 | Overbooking | Not allowed by default; a doctor's schedule can allow "up to N extra" per session | PO | |
| D12 | No-show | Marked automatically at the end of the session if not checked in; front desk can undo the same day | PO | |
| D13 | Who sees a patient's clinical record? | Doctors and nurses of the **department** where the patient has a visit (any time), plus anyone the patient is booked with today; others need **emergency access** with a reason, reviewed later | DR, PO | |
| D14 | Emergency ("break-glass") access | Allowed for doctors and nurses; reason required; 4 hours; every use emailed to the medical records officer and reviewed weekly | DR | |
| D15 | Consultation note format | Structured: Complaint, History, Examination, Assessment, Plan (free text in each); templates per department later | DR | |
| D16 | Who signs notes? | The author signs. After signing a note cannot be edited: changes are **amendments** with a reason; wrong-patient notes are marked "entered in error" (never deleted) | DR | |
| D17 | Unsigned notes | Drafts older than 24 hours appear on the doctor's worklist and the HOD's report | DR | |
| D18 | Diagnosis codes | India: **ICD-10 (WHO)**; US: **ICD-10-CM**. Free-text diagnosis allowed only with a reason, to be coded later | DR, LEGAL (licence) | |
| D19 | Allergies | Coded categories (drug/food/environment/other), free-text substance in Phase 2 (drug codes come with pharmacy); "No known allergies" must be recorded explicitly | DR | |
| D20 | Vitals | BP, pulse, temperature, respiratory rate, SpO₂, height, weight (BMI calculated), pain score. Impossible values refused; abnormal values flagged using ranges **you approve** (part 01 §6) | DR | |
| D21 | Medications in Phase 2 | Only a **patient-reported current medicines list** (no prescriptions until Phase 4)? Or bring simple OPD prescriptions forward? | DR, PO | |
| D22 | Consultation fee / billing in Phase 2 | Not in Phase 2 (Phase 5). If needed earlier, a simple "fee collected yes/no" note on the visit | PO | |
| D23 | Confidential (VIP/staff) patients | A "restricted record" flag: hidden from general search, every opening recorded and reported | PO, DR | |
| D24 | Retention of patient records | Never deleted by users; legal retention period per country to be set by LEGAL before go-live | LEGAL | |
| D25 | Patient photo | Not in Phase 2 (privacy + storage); add later if wanted | PO | |
| D26 | Languages / local scripts | Names stored as typed (Unicode, any script); screens in English for Phase 2 | PO | |

## Sign-off (spec 26.10)

| Role | Name | Decision | Date |
|---|---|---|---|
| Product owner | | ☐ Approved ☐ Approved with changes ☐ Not approved | |
| Reviewing doctor (clinical governance) | | ☐ Approved ☐ Approved with changes ☐ Not approved | |
| Legal/compliance (D6, D7, D9, D18, D24) | | ☐ Approved ☐ Pending (build may start; go-live waits) | |

Engineering can start slice 2A (registration and search) once PO and doctor sign; legal items
must be closed before any real patient data is entered (spec 26.7).
