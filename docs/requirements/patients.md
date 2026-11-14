# Requirement records: patients (Phase 2, HIMS-PAT)

Records in the fourteen fields of spec 25.4 for the patient tickets of Phase 2 (design:
[Phase 2 P0](../p0/phase-2-patients/README.md), approved for now on 2026-11-08). How to read a
record: [README](README.md). Every endpoint with its full contract:
[API contracts: patients](../architecture/api-and-integrations/endpoints/patients.md).

### HIMS-PAT-001

| Field | Record |
|---|---|
| ID and title | HIMS-PAT-001 Patient registration with MRN, contacts, relationships, ID numbers (encrypted, masked) and consents |
| Business/clinical reason | Every later clinical step needs one reliable record per person, with a hospital-facing number (MRN) that never changes (spec 4.5, 9). Rules: P0 part 01 section 1, decisions D1-D3, D6-D9, D26. Owner: PO; D6/D7/D9 confirmed for now by LEGAL (go-live item) |
| Actors | `patients.register` (Receptionist / front desk at a facility; Medical records officer), `patients.view` and `patients.search` (also administrators and heads of department, who do not register) |
| Preconditions | Hospital provisioned with an active MRN numbering scheme (made at provisioning); a facility; Patient registration feature on for that facility |
| Main success path | Front desk enters a name (one is enough), sex, date of birth or age, a mobile or "No phone"; optionally address, people (guardian, next of kin), ID numbers and consents; the MRN is issued in the same transaction; the record opens. Later: correct details (an old name stays as an alias), add / change / end contacts and people, add / end ID numbers, record consent decisions |
| Alternate/failure paths | Missing name / sex / age → 400 next to the field; future or >130-year birth date → 400; invalid phone → 400; MRN scheme missing → 409 and nothing saved; a one-per-person ID number (ABHA, Aadhaar, passport, SSN) already on another patient → 409 naming that MRN; wrong Aadhaar check digit → 400; kind not used in the hospital's country → 400; under 18 without a parent or guardian → 400 unless a reason is given; unknown patient without "how they arrived" → 400; stale version → 409; feature off at the facility → refused; another facility than the person's grant → 403 |
| Data effects | `patients`, `patient_contacts`, `patient_relationships`, `patient_identifiers`, `patient_consents` (append-only), `patient_aliases` (append-only), `patient_identifier_keys`; one MRN in `issued_numbers`; outbox event `patient.registered` (ids only) |
| Security classification | Restricted (personal) for names, contacts and numbers; Clinical for sex, gender identity, pronouns and reported blood group (data dictionary, new level). ID numbers encrypted with the field keys, shown masked, found by a keyed fingerprint ([ADR-036](../decisions/ADR-036-patient-id-numbers.md)) |
| Audit requirement | `patient.registered`, `patient.updated`, `patient.record.viewed`, `patient.searched`, `patient.contact.added`, `patient.contact.updated`, `patient.relationship.added`, `patient.relationship.updated`, `patient.identifier.added`, `patient.identifier.ended`, `patient.consent.recorded`; ID numbers appear only masked; an MRN look-up records that it happened and how many matched, not what was typed |
| Idempotency/concurrency | Registration and every add accept an Idempotency-Key (a double click gives one patient and one MRN); edits carry `version` (409 when stale); the MRN counter row is locked until the registration commits; a unique index refuses the same one-per-person number twice, even at the same moment |
| Integration dependencies | None. UIDAI and ABDM checks come later (Phase 6); numbers are marked "not verified" |
| Acceptance criteria | Register with an age only → MRN issued, birth date estimated (1 July); a retried request → one patient; the same Aadhaar on a second patient → refused naming the first MRN; the full number never appears in a response, the console or the audit log; administrators open records but cannot register; every opening is in the audit log; a name change keeps the old name searchable |
| Test evidence | `apps/patients/tests/test_patient_registration.py`, `apps/demo/tests/test_demo_hospitals.py`; screens `frontend/src/features/patients/PatientsPage.test.tsx`; browser test `frontend/e2e/tests/06-patients.spec.ts`; manual steps [patient registration](../workflows/patient-registration.md). Reviewer: the PO, at PR review |
| Release risk | Privacy: patient data. Synthetic data only until LEGAL closes D6, D7, D9, D24 and hosting moves to the paid stage. Rollback: the feature can be switched off per facility; the migration only adds tables |

### HIMS-PAT-002

| Field | Record |
|---|---|
| ID and title | HIMS-PAT-002 Patient search: MRN, phone, ID number or similar name, with minimal results; every search audited |
| Business/clinical reason | The front desk must find a returning patient before registering, so nobody gets two records (P0 part 01 sections 1 and 2; spec 4.5 duplicate prevention, 28.6 "patient search by approved demographic/search index, with privacy constraints"). Indian and US names are often written several ways (Lakshmi / Laxmi, Mohammad / Muhammad) ([ADR-037](../decisions/ADR-037-patient-search.md)). Owner: PO |
| Actors | `patients.search` (Receptionist / front desk, Medical records officer, hospital administrator, head of department); not the auditor, basic staff or the supplier's support account |
| Preconditions | Patients registered (HIMS-PAT-001); the `pg_trgm` extension (added by migration `patients.0002`) |
| Main success path | One box on Patients: type the MRN (or only its number), a phone number, an ID number or a name (any spelling, any order, earlier names too; a number among the words is an age); optionally sex and age. The best 50 matches are listed with what found each one; the record opens from the MRN |
| Alternate/failure paths | Fewer than 3 letters of a name → 400 "Type at least 3 letters"; two ages or an age over 130 → 400; more than 50 matches → the best 50 and the total, with "add the age, the sex or more of the name"; a number nobody has → no results (not an error); an ended ID number → not found; no `patients.search` → 403 |
| Data effects | Reads only. New column `patients.search_sounds` (sound keys of every name and earlier name) filled at registration, at every name change and for existing patients by the migration; two GIN indexes on `patients` (a trigram index on the search names, and one on the sound keys) |
| Security classification | Restricted (personal) data in the request; results show only name, MRN, age and sex, the phone's last 4 digits, the facility and what matched. ID numbers are compared by their keyed fingerprint, never in plain text. The address with the search words is kept out of the server's access log and traces (path only, ADR-021) |
| Audit requirement | `patient.searched` for every search, in the app and in the admin console: what kind of search (MRN, phone, ID number, name), the number of results and the filters used (names only), never what was typed. Opening a record stays `patient.record.viewed` |
| Idempotency/concurrency | Read-only; no idempotency key or version needed |
| Integration dependencies | None |
| Acceptance criteria | "suneeta" finds Sunita, "laxmi" finds Lakshmi, "kumar ravi" finds Ravi Kumar; an earlier family name still finds the patient; the full phone finds every patient who gave it (not relatives' phones); a typed Aadhaar finds its patient by fingerprint; "1" finds MRN-00000001 and not MRN-00000011; more than 50 matches show 50 and the total; every search is audited without its words; the console uses the same search; the name search can use its indexes |
| Test evidence | `apps/patients/tests/test_patient_search.py`, `apps/patients/tests/test_patient_registration.py`, `apps/demo/tests/test_demo_hospitals.py`; screens `frontend/src/features/patients/PatientsPage.test.tsx`; browser test `frontend/e2e/tests/06-patients.spec.ts`; manual steps [patient search](../workflows/patient-search.md). Reviewer: the PO, at PR review |
| Release risk | Low: read-only and one added column with indexes (expand only). Rollback: the previous screen still lists patients; the migration's column and indexes can stay. Results never include "last visit": that comes with visits (HIMS-CLIN-001); restricted records are hidden from search with HIMS-PAT-006 |

### HIMS-PAT-005

| Field | Record |
|---|---|
| ID and title | HIMS-PAT-005 Patient chart header and overview; the record's history for medical records |
| Business/clinical reason | Every screen that shows a patient must keep who it is and what could harm them in view (spec 15.3; P0 part 01 section 7: name, MRN, age and sex, allergies, flags). Medical records must see who opened a chart (P0 part 04 matrix; spec 13.4). Owner: PO; the header's contents [DR] |
| Actors | `patients.view` (front desk, medical records, hospital administrator, head of department): header, alerts, Overview and Demographics; `patients.history` (Medical records officer only): History |
| Preconditions | Patients registered (HIMS-PAT-001); after `migrate`, the Medical records officer role holds `patients.history` |
| Main success path | Open a patient from Patients: the header (name, MRN, age and sex, "Allergies not asked yet", unknown / merged flags, preferred name) stays below the menu bar on every tab; alerts below it; Overview shows the clinical summary (none recorded yet), contact, guardian and emergency contact, ID numbers (masked), consent in force and where the record came from; Demographics is HIMS-PAT-001's record with its changes; History lists who opened and changed the record, newest first, 50 a page |
| Alternate/failure paths | No `patients.history` → no History tab, `?tab=history` shows Overview, the API answers 403; no `patients.view` → 403 as before; a record with nothing to warn about → no alerts |
| Data effects | Reads only: the patient's record, and the audit log rows for its id (served by the index on resource and time). Writes one audit event for each History view. No new tables or columns |
| Security classification | Restricted (personal): the header and overview show what the record already showed, ID numbers masked. History shows staff names, places, event names and the **names** of corrected fields, never their values (those stay in the audit log for auditors) |
| Audit requirement | Opening the chart stays `patient.record.viewed`; new `patient.history.viewed` (resource the patient; `in: console` from the admin console) |
| Idempotency/concurrency | Read-only; no idempotency key or version needed |
| Integration dependencies | None |
| Acceptance criteria | The header shows on every tab; "Allergies not asked yet" is shown while nothing is recorded (D19); a child without a guardian, a missing privacy notice, an unknown patient and a missing contact each give their alert, in the app and the console; the medical records officer sees registered, opened and corrected events with field names only; the front desk and the administrator get 403 and no tab; viewing the history is audited; the supplier's support account never holds `patients.history` |
| Test evidence | `apps/patients/tests/test_patient_chart.py`, `apps/demo/tests/test_demo_hospitals.py`; screens `frontend/src/features/patients/PatientsPage.test.tsx`; browser test `frontend/e2e/tests/06-patients.spec.ts` (the chart); manual steps [patient chart](../workflows/patient-chart.md). Reviewer: the PO, at PR review |
| Release risk | Low: reads only, no migration. Rollback: revert the PR; the permission stays in the catalogue unused. Visits, Notes and Vitals tabs, recorded allergies, restricted and deceased flags come with HIMS-CLIN-001/002/003/005, HIMS-PAT-006 and HIMS-PAT-007 |
