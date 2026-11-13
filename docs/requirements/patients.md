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
