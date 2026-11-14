# Artifact A review: patients and the MPI (HIMS-DATA-003)

**Phase 2 → Spec §28, §4.5 → Slice 2A → HIMS-DATA-003.** Spec 28.8: "Artifact A is accepted when
all implemented P0 domains have reviewed physical schemas, data dictionaries, constraints,
source-of-truth ownership, sensitive-data classification, indexes for critical query patterns,
retention/correction rules, migration procedures and automated tests for critical invariants."

This page is that review for the **patient / master patient index (MPI) domain** as built in
slice 2A (HIMS-PAT-001 registration, PAT-002 search, PAT-005 chart header, PAT-006 restricted
records). Reviewed 2026-11-14. Columns, types, keys and sensitivity of each table are in the
generated [data dictionary](data-dictionary.md) and [ERD](erd.md); how the tables fit is in
[patients.md](patients.md); the design is [Phase 2 P0 part 02](../../p0/phase-2-patients/02-database-design.md).

**Result: accepted for the built patient tables**, after seven fixes this review found (section
11). It is repeated when HIMS-PAT-003 (duplicate warning), PAT-004 (merge and undo), PAT-007
(recording a death) and the clinical tables (HIMS-CLIN-*) change these tables.

## Spec 28.8 checklist

| Criterion | Evidence | Result |
|---|---|---|
| Reviewed physical schemas | Section 1: eight tables, keys, business identity, constraints, indexes, size at a 500-bed hospital | ✅ |
| Data dictionaries | [data-dictionary.md](data-dictionary.md) "Patients" section, generated from the models; CI fails when stale (`data_dictionary --check`) | ✅ |
| Constraints | Section 1; each one broken on purpose in `apps/patients/tests/test_data_invariants.py` | ✅ |
| Source-of-truth ownership | Section 2 (spec 28.3: "Patient/MPI domain within each customer deployment") | ✅ |
| Sensitive-data classification | Section 3: every column Restricted, Clinical, Secret or Internal; access matrix by role | ✅ |
| Indexes for critical query patterns | Section 4: 15 patient queries and 12 patient screens (10 in the app, 2 in the console) measured at hospital size with query plans | ✅ after the fixes (one accepted limit, section 11) |
| Retention and correction rules | Section 5 | ✅ (retention periods 🔒 LEGAL, as for the whole hospital) |
| Migration procedures | Section 8: migrations `patients.0001`–`0004` reviewed | ✅ |
| Automated tests for critical invariants | Section 9: `test_data_invariants.py` (11 tests) plus the services' tests; a test fails when a new database rule has no test | ✅ |

## 1. Physical schema

Rows at hospital size are what the [volume check](volume-check.md) uses for a 500-bed hospital
(about 150,000 new patients a year; a little over three years of registrations).

| Table | Key and business identity | Database rules | Indexes (besides the primary key and foreign keys) | Rows at hospital size |
|---|---|---|---|---|
| `patients` | UUID `id`; **MRN unique within the hospital** (`patients_mrn_unique`: organization, MRN) | `patients_merged_has_target`, `patients_not_merged_into_self`, `patients_restriction_has_kind`, `patients_version_check` | `patients_dob_idx`, `patients_facility_idx` (facility, newest), `patients_search_name_trgm` (trigram), `patients_search_sounds_idx` (sound keys), **`patients_created_idx`** (newest first; HIMS-DATA-003), **`patients_mrn_number_idx`** (the MRN's number part; HIMS-DATA-003) | 500,000 |
| `patient_contacts` | UUID | `patient_contacts_phone_has_number`, `patient_contacts_email_has_address`, version | `patient_contacts_phone_idx` | 800,000 (a mobile each, an address for 6 in 10) |
| `patient_relationships` | UUID | `patient_relationships_not_self`, version | — | 100,000 |
| `patient_identifiers` | UUID; the number is found by its keyed fingerprint `value_hash`, never by the number | `patient_identifiers_unique_number` (one active number per person for Aadhaar, ABHA, passport, SSN), version | `patient_identifiers_hash_idx`, **`patient_ids_prev_mrn_idx`** (hospitals with previous MRNs; HIMS-DATA-003) | 300,000 |
| `patient_consents` | UUID | append-only (trigger `patient_consents_history`) | `patient_consents_idx` (patient, kind, newest) | 650,000 |
| `patient_aliases` | UUID | append-only (trigger `patient_aliases_history`) | **`patient_aliases_merged_mrn_idx`** (earlier MRNs only; HIMS-DATA-003) | 10,000 |
| `patient_emergency_access` | UUID | `patient_emergency_access_reviewer_not_user`, `patient_emergency_access_review_complete`, version | `patient_emergency_user_idx`, `patient_emergency_review_idx` | 2,000 |
| `patient_identifier_keys` | UUID; one row per hospital | — | — | 1 |

Every foreign key is `PROTECT`: a patient with any record cannot be deleted, and the database's
own foreign keys refuse it too (tested). Business numbers are separate from database keys
(spec 28.2): the MRN, earlier MRNs (`patient_aliases`, kind `merged_mrn`) and another
hospital's MRN (`patient_identifiers`, kind `previous_mrn`, fingerprinted with the issuing
hospital, because two hospitals may use the same number). The MRN is never assumed unique
across hospitals: each hospital has its own database (ADR-003) and its own MRN scheme.

## 2. Ownership and sources of truth (spec 28.3)

| Data | Owner and only writer | Others |
|---|---|---|
| Patient identity, demographics, contacts, people, ID numbers, consents, earlier names | Patient/MPI domain: `apps/patients/services.py` (registration, corrections, ending, consents) | The admin console uses the same services. Later domains (visits, orders, billing) refer to `patients.id` and read through the domain; they never write these tables. |
| The MRN value | Numbering domain issues it (`issued_numbers`, counter per scheme) inside the registration transaction; the patient row holds it | Never typed, never changed after registration; a merge (HIMS-PAT-004) keeps the other record's MRN as an earlier MRN |
| Restriction (VIP, staff, other) and emergency access | `apps/patients/restricted.py` | Medical records decide; reviews are made by someone other than the user (database rule) |
| Who opened or searched a record | Audit domain (`audit_events`, `patient.*` events) | Read by auditors; medical records read a record's history and restricted openings through the patient screens |
| ID number checks with the issuer (UIDAI, ABDM) | Not built: every typed number is "not verified" | When ABDM verification comes (🔒 VENDOR), ABDM is the source of truth for ABHA; the response and its meaning will both be kept (spec 28.3, eligibility rule applied by analogy) |

## 3. Classification and access

Every patient column has a sensitivity in the [data dictionary](data-dictionary.md) (rules in
`backend/common/datadict/catalog.py`, `PATIENT_TABLES`):

| Level | Patient columns |
|---|---|
| **Clinical (PHI)** | sex, gender identity, pronouns, reported blood group; the reason given for emergency access (it may describe the patient's state) |
| **Restricted** (personal) | MRN, names, earlier names, birth date, contacts, people, ID numbers (encrypted value and masked copy), consents, the restriction and its kind, search columns (`search_name`, `search_sounds`), notes |
| **Internal** | the keyed fingerprint of an ID number (`value_hash`: no number can be worked back from it without the hospital's key) and system columns |
| **Secret** | the hospital's fingerprint key (`patient_identifier_keys.key_encrypted`): never shown, exported or read by the reporting database user |

**Who can do what** (system roles; custom roles combine these permissions; patient permissions
are given only by administrators who themselves hold `patients.view`, and are never given to the
supplier's support access):

| Data and action | Front desk (receptionist) | Medical records | Head of department (doctor) | Hospital administrator | Auditor |
|---|---|---|---|---|---|
| Search and list patients: name, MRN, age, sex, last 4 digits of the mobile, where registered (minimum necessary) | ✅ | ✅ | ✅ | ✅ | — |
| Open a record (every opening audited) | ✅ | ✅ | ✅ | ✅ | — |
| Register; correct demographics, contacts, people, ID numbers; record consent | ✅ | ✅ | — | — | — |
| A full ID number | nobody: masked everywhere, in the app, the console and the audit log | | | | |
| Record history (who opened and changed it) | — | ✅ | — | — | (whole audit log) |
| Restricted (VIP, staff) records | hidden from search; exact MRN shows "Restricted record" only | ✅ open; restrict and lift with a reason | open only with **emergency access** (4 hours, reason, medical records emailed) | hidden | (audit log) |
| Review emergency access; list restricted openings | — | ✅ (never their own) | — | — | — |
| Audit log of every patient read and search | — | — | — | — | ✅ |

Restricted records, record correction and emergency access need two-factor sign-in
(`MFA_REQUIRED_PERMISSIONS`). Below the app ([database users](../../workflows/database-users.md)):
the app's database user reads and writes these tables but cannot change or delete the
append-only ones (triggers); the read-only reporting user reads every column except the Secret
key. **Open point (not a blocker for slice 2A):** whether the reporting user should see patient
names and contacts at all is decided with reporting (minimum necessary for reports), before real
patient data.

## 4. Indexes and the queries they serve (spec 28.6)

The patient part of the [volume check](volume-check.md): 500,000 invented patients with their
contacts, ID numbers, consents, people, earlier names, restricted records, emergency access and
500,000 patient audit events. Each query's plan is read from PostgreSQL and must use its index
within 100 ms; each screen's p95 must be within 300 ms (one record) or 500 ms (searches and
lists).

**Final run (2026-11-14, `volume_check --scale 1`, PostgreSQL 18.4 on the developer PC, 5.9
million rows): all 40 queries use their index in time and all 42 screens are within target.**
Recorded on the Performance screen (group **Patients**). Details and the first run's problems:
[volume check](volume-check.md#patients-and-the-mpi-hims-data-003).

| Query (what the app does) | Index used | Time at 500,000 patients |
|---|---|---|
| Patients, newest registrations first | `patients_created_idx` | 0.7 ms |
| Patients registered at one facility | `patients_facility_idx` | 0.1 ms |
| Search: exact MRN (within the hospital) | `patients_mrn_unique` | 0.2 ms |
| Search: an earlier MRN after a merge | `patient_aliases_merged_mrn_idx` | 0.1 ms |
| Search: the MRN's number part ("123") | `patients_mrn_number_idx` | 0.2 ms |
| Search: phone number | `patient_contacts_phone_idx` | 0.2 ms |
| Search: ID number, by fingerprint | `patient_identifiers_hash_idx` | 0.1 ms |
| Search: hospitals with previous MRNs (a number found nowhere else) | `patient_ids_prev_mrn_idx` | 0.0 ms |
| Search: given and family name (spelling or sound) | `patients_search_sounds_idx` + `patients_search_name_trgm` | 12.6 ms |
| Search: one name only, the commonest family name (30,000 matches ranked) | the same two | 294 ms (allowed 400 ms; decisions log row 36) |
| Record: consent decisions, newest first | `patient_consents` patient index | 0.2 ms |
| Record history | `audit_resource_idx` | 0.3 ms |
| Restricted record: is my emergency access open? | `patient_emergency_user_idx` | 0.1 ms |
| Emergency access waiting for review | `patient_emergency_review_idx` | 1.4 ms |
| Restricted record openings, last 7 days | `audit_action_idx` | 7.3 ms |

| Screen | p95 | Target | Database queries |
|---|---|---|---|
| Patients (newest first) | 104 ms | 500 ms | 8 |
| Patient search: exact MRN / MRN number / phone | 23 / 25 / 23 ms | 500 ms | 14–15 |
| Patient search: given and family name | 56 ms | 500 ms | 11 |
| Patient search: one common family name | 301 ms | 500 ms | 11 |
| Patient record (chart header and overview) | 36 ms | 300 ms | 13 |
| Patient record history | 19 ms | 500 ms | 9 |
| Emergency access waiting for review | 25 ms | 500 ms | 6 |
| Restricted record openings | 32 ms | 500 ms | 9 |
| Console: patients / emergency access | 100 / 94 ms | 500 ms | 7 / 8 |

The number of database queries per screen does not grow with the records (CI test).

## 5. Lifecycle, retention and correction

* **Nothing is deleted.** Contacts and people are ended (`is_active`), ID numbers are ended
  with who, when and why, a merged record stays with `status = merged` and a pointer to the
  record kept (HIMS-PAT-004). Foreign keys refuse deleting a patient with any record; the
  console has no delete button.
* **History tables never change:** consents (a new row for each decision) and earlier names
  refuse updates and deletes in the database, except moving them to the record kept by a merge
  (`patient_id` only).
* **Corrections** go through the normal screen with a version check; the before and after
  values are in the audit log, and the record's history shows the names of the fields that
  changed, never the values.
* **Restriction** is set and lifted with a reason (audited); emergency access rows are kept with
  their review.
* **Retention:** patient records and their audit events are not in the retention purge
  (HIMS-COMP-006 covers housekeeping tables only; the audit log is kept, HIMS-COMP-007). How long
  medical records are kept after the last visit is a legal decision (🔒 LEGAL, ADR-013), as for
  the rest of the hospital. Archiving comes with that decision.

## 6. Transactions and concurrency

* **Registration is one transaction:** the MRN is issued (the scheme's counter row is locked),
  the patient, contacts, people, ID numbers, consents and audit event are written, or none are.
  A failed registration uses no number; a retried one with the same `Idempotency-Key` returns the
  same patient.
* **Every change checks the version** the person saw (row locked, `SELECT … FOR UPDATE`); a stale
  save gets 409. The search columns are worked out in the same save as the names.
* **Two front desks entering the same Aadhaar number at once:** the unique index decides; the
  second gets "This number was just recorded for another patient. Search for it first."
* **Emergency access:** opening locks the patient row, then checks for an open one (409 if
  open), so two clicks at the same moment open one. Reviews check the version; the database
  refuses a review by the user themselves.
* **Emails** (emergency access) are sent after the transaction commits, so a rolled-back change
  sends nothing.

## 7. History and versions

* The patient row is the current state; every earlier state is in the tamper-evident audit log
  (before/after values; hash chain).
* Consents: one row per decision, newest first. Earlier names: one row per name change.
* ID numbers: ended rows stay, with the reason.
* Reads: every opening (`patient.record.viewed`, with `restricted: true` and how it was opened
  for restricted records), every search (`patient.searched`: the kind and result count, never
  what was typed) and every history view are audit events.
* Clinical facts (allergies and later) follow spec 28.5 when HIMS-CLIN-003 adds them.

## 8. Migrations

| Migration | What it does | Review |
|---|---|---|
| `patients.0001` | Six patient tables, the fingerprint key table and the history triggers | New tables only. |
| `patients.0002` | `pg_trgm` extension, `search_sounds` column filled for existing patients, two GIN indexes | The extension needs the database owner (the migration user); the fill reads patients in chunks of 500 and was run while the tables were small. **For a hospital with patients, a fill like this runs as a re-runnable command in batches** (playbook in [README section 7](README.md#7-migrations-and-backfills)). |
| `patients.0003` | Restriction columns (with defaults, so existing rows need no fill) and the emergency access table | Additive. |
| `patients.0004` (HIMS-DATA-003) | `patients_created_idx`, `patients_mrn_number_idx`, `patient_aliases_merged_mrn_idx`, `patient_ids_prev_mrn_idx` | Built `CONCURRENTLY` (no lock on the patient register while it builds; `atomic = False`), as HIMS-DATA-002 did. Took 11 seconds on the 500,000-patient copy. |
| `numbering.0002` (HIMS-DATA-003) | `issued_numbers_created_idx` (the console's list of every number) | Built `CONCURRENTLY`, so issuing MRNs is not blocked. |

Every hospital database is migrated after a merge (India, then US, then the hosted Development
database), as in [database-migrations.md](../../workflows/database-migrations.md).

## 9. Automated tests for critical invariants

* `apps/patients/tests/test_data_invariants.py` (HIMS-DATA-003): each test breaks one database
  rule past the services and expects a refusal: one MRN per patient, a merged record points at
  another record, a restricted record says why, versions never below zero, a phone has a
  number and an email an address, nobody is their own relative, one person per ID number, the
  emergency access review rules, history rows never change except by a merge, patients are
  never deleted. The last test lists every constraint, unique index and trigger on the patient
  tables and fails when one has no test.
* The services' own tests: registration (`test_patient_registration.py`), search
  (`test_patient_search.py`), chart (`test_patient_chart.py`), restricted records
  (`test_restricted_records.py`).
* The volume check's index test (`apps/performance/tests`) keeps each patient query on its
  index, and fails when a patient screen makes one more database query per row.

## 10. Catalogs, data flows and test data

* **Catalogs** are code: sex, marital status, blood group, relations, consent kinds, restriction
  kinds, ID number kinds and their checks per country (`identifiers.py`: Aadhaar check digit,
  ABHA, passport, SSN, voter ID, driving licence), sound-alike spelling rules (ADR-037). Stored
  values are codes; labels may change. They change by a code change and a reviewed PR.
* **Data flows:** the only message is the emergency access email to medical records: who opened
  a record and when, with a link; **no patient name, MRN or reason** (the message catalog says
  so). No external system receives patient data yet (ABDM, SMS: later, each with its lineage
  entry). Logs and traces never carry query strings (so never search words such as a
  patient's name), nor values written under names like `patient`, `phone` or `given_name`
  (`common/log_safety.py`).
* **Test and demo data** are invented: the demo hospitals' patients (`apps/demo/patients.py`),
  the tests' patients, and the volume check's 500,000 patients, whose names are made of
  syllables that belong to nobody.

## 11. What this review found and fixed

The first full-size run (500,000 patients, 5.9 million rows in all) and the code review found
seven problems. All are fixed; the numbers are from that run and from the copy after each fix.

| # | Found | At hospital size, before | Fix | After |
|---|---|---|---|---|
| 1 | The patient list (newest registrations) had no index: every patient was read and sorted | 306 ms; screen p95 611 ms (over the 500 ms target) | `patients_created_idx` | 0.6 ms; screen p95 114 ms |
| 2 | Searching the MRN's number part ("123") matched a pattern against every MRN | 400 ms; screen 459 ms | `patients_mrn_number_idx` on the MRN's last digits without leading zeros; same results | 0.2 ms; screen 23 ms |
| 3 | An earlier MRN kept after a merge, and the hospitals with previous MRNs on record, were found by reading whole tables (the second also returned each hospital many times: the model's ordering leaked into DISTINCT) | `patient_aliases` read whole; 87 ms over 300,000 ID numbers on every number not found | `patient_aliases_merged_mrn_idx`, `patient_ids_prev_mrn_idx`; ordering set in `previous_mrn_issuers()` | 0.1 ms; 0.0 ms |
| 4 | The exact-MRN look-up did not name the hospital, while the MRN index starts with it. PostgreSQL 18 on the developer PC hides this (skip scan); CI and hosting run PostgreSQL 17, which cannot use the index that way | 0.3 ms on the PC; a whole-index read on 17 | The look-ups name the hospital (`search.mrn_matches`, the list's `?mrn=`) | the index on both versions |
| 5 | The hospital's time zone was read from the database once per row (each patient's age, each "Ends" time) | 61 queries for a name search, 32 for the list, 107 for the console's emergency access list | Read once per request (`common/request_context.request_memo`, `organizations/dates.py`); cleared when Hospital settings change it | 11, 8 and 8 queries |
| 6 | The console's patient list counted every patient twice; its issued-numbers list sorted all 300,000 numbers on every page | 1,119 ms; 513 ms (both over 500 ms) | Patient tables use the console's capped counting (up to 10,000, as the audit log does); `issued_numbers_created_idx` | 162 ms; 130 ms |
| 7 | A one-word search for the commonest family name (30,000 matches) counted all of them again after ranking them | 344 ms query; screen p95 529 ms | The total is counted up to 1,000 ("More than 1,000 patients match"); the cheap sound key is checked before the spelling (a quarter faster) | screen within 500 ms (final run below) |

One limit remains and is accepted for now (decisions log row 36): ranking 30,000 matches by
closeness takes a few hundred milliseconds, and it grows with the register. Its query may take up
to 400 ms (the others 100 ms) while its screen stays within 500 ms. Before a hospital's register
passes about 2 million patients, a nearest-first trigram index replaces the ranking
(HIMS-PAT-009).

Also found and recorded for later: the read-only reporting user can read patient names and
contacts (HIMS-IAM-023, before real patient data); the later P0 domains need the same review
(HIMS-DATA-004). The console had no page for "restricted record openings", which the app's
Emergency access page has (HIMS-PAT-006): added, for medical records, audited the same way.

## 12. Re-review triggers

Repeat this review when a patient table gains a column, rule or index, when HIMS-PAT-003, 004 or
007 is built, when a clinical table refers to patients, and before the first real patient is
registered (with the retention decision and the reporting user's access).
