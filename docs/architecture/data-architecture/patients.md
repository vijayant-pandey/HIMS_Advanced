# Patients: tables and rules (HIMS-PAT-001)

Design: [Phase 2 P0 part 02](../../p0/phase-2-patients/02-database-design.md) (approved for now,
2026-11-08). Columns, keys and sensitivity of each table are in the generated
[data dictionary](data-dictionary.md) and [ERD](erd.md). This page says how the parts fit.

## Tables

| Table | Holds | Lifecycle |
|---|---|---|
| `patients` | One row per person: MRN, names, birth date (estimated when an age was given), sex, language, reported blood group, unknown-patient flag, where and by whom registered | Never deleted; edits versioned and audited; merged records stay (HIMS-PAT-004) |
| `patient_contacts` | Mobile, other phones (E.164), email, address; one main per kind | Ended, not deleted |
| `patient_relationships` | Mother, father, guardian, spouse, next of kin, emergency contact, caregiver; optional link to another patient | Ended, not deleted |
| `patient_identifiers` | ID numbers: encrypted value, masked copy, keyed fingerprint, "not verified" | Ended with a reason, not deleted |
| `patient_consents` | Privacy notice, SMS, email decisions: a new row each time | Append-only (trigger) |
| `patient_aliases` | Earlier names (and, after a merge, earlier MRNs) | Append-only (trigger) |
| `patient_identifier_keys` | The hospital's random fingerprint key, encrypted | One row, never changes |

## Rules worth knowing

* **The UUID is the identity, the MRN is the hospital's number** (spec 4.5). The MRN comes from
  the hospital-wide MRN scheme ([numbering](numbering-schemes.md)) inside the registration
  transaction: a failed registration uses no number, a retried one (same Idempotency-Key) gets
  the same patient. One MRN in every facility.
* **Hospital-wide visibility.** A grant for `patients.search` / `patients.view` at any facility
  shows every patient of the hospital (permission scope `any_grant`): a patient registered in
  Noida is found in Dwarka. Registering checks the facility of registration.
* **Minimum necessary.** The list shows name, MRN, age and sex, the mobile's last 4 digits and
  where registered. The record shows ID numbers masked only.
* **Reading is audited**: opening a record (`patient.record.viewed`), an MRN look-up
  (`patient.searched`, without what was typed). Patient search by phone, ID and similar name
  arrives with HIMS-PAT-002 (it adds the trigram index on `search_name`).
* **Patient search (2026-11-13, HIMS-PAT-002, [ADR-037](../../decisions/ADR-037-patient-search.md)).** Migration
  `patients.0002` adds the `pg_trgm` extension, the column `search_sounds` (an array of the sound
  keys of every name and earlier name, e.g. Lakshmi and Laxmi are both `lxm`; filled for existing
  patients) and two GIN indexes: `patients_search_name_trgm` (trigram, on `search_name`) and
  `patients_search_sounds_idx`. Both columns are refreshed at registration and every name change.
  Exact look-ups use the existing indexes: `patients_mrn_unique`, `patient_contacts_phone_idx`,
  `patient_identifiers_hash_idx`. Every search is audited (`patient.searched`: kind, result count
  and filter names only).
* **Patient chart (2026-11-14, HIMS-PAT-005).** No new tables. The chart header's alerts are
  worked out from the record (`apps/patients/chart.py`); the record's history reads the audit
  log rows for the patient's id through the existing index `audit_resource_idx` (resource type,
  id, time) and shows field names only. Viewing it adds `patient.history.viewed`.
* **Restricted records and emergency access (2026-11-14, HIMS-PAT-006).** Migration
  `patients.0003`: `patients.is_restricted` and `patients.restriction` (vip, staff, other;
  check `patients_restriction_has_kind`: both set or both empty), and the table
  `patient_emergency_access` (patient, user, reason, `expires_at` = opened + 4 hours,
  `ended_at` when ended early, `reviewed_at`, `reviewed_by`, `outcome`, `review_note`,
  `version`). Checks: the reviewer is never the user
  (`patient_emergency_access_reviewer_not_user`); a review has its time and outcome together
  (`patient_emergency_access_review_complete`). Indexes: `patient_emergency_user_idx` (user,
  patient, newest expiry: "is my emergency access open?" on every opening) and
  `patient_emergency_review_idx` (review state, newest first). Never deleted. The reason is
  classified **Clinical** (it may describe the patient's state). Restricted openings are
  found in the audit log (`patient.record.viewed` with `restricted: true`).
* **ID numbers**: [ADR-036](../../decisions/ADR-036-patient-id-numbers.md).
* **History tables**: `patient_consents` and `patient_aliases` refuse updates and deletes in the
  database (`patient_history_guard()`), except a change of `patient_id`, which only a merge
  (HIMS-PAT-004) will make.
* **Sensitivity**: a new **Clinical** level in the data dictionary for health-related columns
  (sex, gender identity, pronouns, reported blood group); everything else about a patient is
  Restricted (personal).

## Not yet (later tickets)

Duplicate warning at registration (HIMS-PAT-003), merge and undo (HIMS-PAT-004), chart header
with allergies (HIMS-PAT-005), restricted VIP/staff records and emergency access (HIMS-PAT-006,
done 2026-11-14, above),
recording a death (HIMS-PAT-007), clinical tables (HIMS-CLIN-*).
