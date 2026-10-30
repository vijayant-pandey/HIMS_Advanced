# 02 Database design (P0-B)

DRAFT. Follows spec 9.3, 26.2 and 28.2 and the existing conventions
([data dictionary](../../architecture/data-architecture/data-dictionary.md)): UUID primary keys,
`organization` on every owned row, `created_at`/`updated_at`, `version` on editable rows,
`PROTECT` on every foreign key (nothing clinical is ever cascade-deleted), times in UTC, dates as
dates. Once built, every table appears in the generated data dictionary with its lifecycle rule.

Sensitivity levels (data dictionary): **R** = Restricted (personal), **C** = **Clinical (PHI)**, a
new level introduced with this phase (stricter: minimum necessary, every read audited, never in
logs/emails), **S** = Secret, **I** = Internal.

## Apps

| App | Tables |
|---|---|
| `patients` | patients, patient_aliases, patient_identifiers, patient_contacts, patient_relationships, patient_consents, patient_duplicate_flags, patient_merges, patient_merge_moves, emergency_access_grants |
| `scheduling` | doctor_schedules, schedule_exceptions, appointments |
| `encounters` | encounters |
| `clinical` | vital_signs, allergies, diagnoses, clinical_notes, clinical_note_versions, reported_medications, icd_codes (catalogue) |

## patients

| Column | Type | Null | Rules | Sens. |
|---|---|---|---|---|
| id | uuid PK | no | | I |
| organization_id | FK organizations | no | | I |
| mrn | varchar(40) | no | unique per organization; issued by numbering (scheme `mrn`) | R |
| status | varchar(16) | no | `active` / `merged` (part 03) | I |
| merged_into_id | FK patients | yes | set only when status = merged | I |
| given_name | varchar(150) | no | | R |
| middle_name, family_name, preferred_name | varchar(150) | no (blank allowed) | | R |
| title | varchar(20) | no (blank) | | R |
| date_of_birth | date | yes | not future; ≤ 130 years | R |
| birth_date_estimated | boolean | no | true when entered as age | R |
| sex | varchar(16) | no | male / female / intersex / unknown | C |
| gender_identity, pronouns | varchar(60) | no (blank) | US optional | C |
| preferred_language | varchar(35) | no (blank) | BCP-47 code, e.g. `hi`, `en-US` | R |
| marital_status, occupation | varchar(30/100) | no (blank) | | R |
| blood_group_reported | varchar(5) | no (blank) | A+, O-…; patient-reported | C |
| is_unknown | boolean | no | unknown/unconscious registration (D3) | I |
| is_restricted | boolean | no | confidential record (D23) | I |
| deceased_at | timestamptz | yes | set by a doctor | C |
| registered_facility_id | FK facilities | no | where registered | I |
| registered_by_id | FK users | yes | | I |
| search_name | varchar(500) | no | normalised "given middle family preferred + aliases", lower case, for search | R |
| version, created_at, updated_at | | | | I |

Constraints: `UNIQUE(organization, mrn)`; `CHECK (status <> 'merged' OR merged_into_id IS NOT NULL)`;
`CHECK (merged_into_id <> id)`.
Indexes: trigram GIN on `search_name` (PostgreSQL `pg_trgm`, for similar-name search and
duplicate detection); `(date_of_birth)`; `(registered_facility_id, created_at)`.

## patient_aliases

Old names and old MRNs (after a name change or a merge), so they stay searchable.
Columns: patient FK, kind (`previous_name` / `merged_mrn` / `other_name`), given/family name or
mrn, recorded_by, created_at. Append-only.

## patient_identifiers

| Column | Type | Rules | Sens. |
|---|---|---|---|
| patient_id | FK | | I |
| kind | varchar(30) | country list (part 05): `abha_number`, `abha_address`, `aadhaar_last4`, `passport`, `voter_id`, `driving_licence`, `previous_mrn`, `us_driver_licence`, `ssn_last4` (only if D7 allows) | I |
| value_encrypted | text | full value encrypted (Fernet, like two-factor secrets); never logged | R |
| value_hash | char(64) | HMAC of the normalised value, for exact search and uniqueness | I |
| value_display | varchar(30) | masked, e.g. `XXXX-XXXX-1234` | R |
| issuer, country | varchar | | I |
| verified | varchar(16) | `unverified` / `verified` (+ verified_by, verified_at, method) | I |
| valid_until | date | null | I |
| is_active | boolean | ended, not deleted | I |

Constraints: `UNIQUE(organization, kind, value_hash) WHERE is_active AND kind IN (unique kinds)`
(ABHA, passport, previous MRN). Aadhaar: only last 4 digits ever stored (D6).

## patient_contacts and patient_relationships

**patient_contacts:** patient, kind (`mobile`/`phone`/`email`/`address`), value fields (phone in
E.164 + phone_hash for search; or email; or address lines, city, district/county, state, postal
code, country), is_primary, is_active, version. **R**.

**patient_relationships:** patient, relation (`mother`, `father`, `guardian`, `spouse`, `child`,
`sibling`, `next_of_kin`, `caregiver`, `emergency_contact`, `other`), is_legal_guardian,
is_emergency_contact, name, phone, related_patient_id (nullable FK patients), valid_from,
valid_until, note, version. **R**.

## patient_consents

patient, kind (`privacy_notice`, `sms`, `email`; later `abdm_linking`, `research`), status
(`given`/`refused`/`withdrawn`), recorded_by, recorded_at, method (`verbal`/`signed_form`), note,
document reference (later). **New row for every change** (history), latest row is current. **R**.

## patient_duplicate_flags

pair (patient_a, patient_b, ordered so a < b), reason (`registration_override`, `found_later`),
score, override_reason, status (`open` / `not_duplicate` / `merged`), raised_by, resolved_by,
resolved_at. `UNIQUE(patient_a, patient_b)`. **I**.

## patient_merges and patient_merge_moves

**patient_merges:** kept_patient, merged_patient, reason, status (part 03:
`requested`/`approved`/`rejected`/`completed`/`undone`), requested_by/at, approved_by/at (must
differ from requester), completed_at, undone_by/at, undo_reason, version. Check:
`kept_patient <> merged_patient`, `approved_by <> requested_by`.

**patient_merge_moves:** merge, table_name, row_id, column_name (always `patient_id`). One row per
moved record, so undo can move exactly those rows back. Append-only.

## emergency_access_grants (D14)

user, patient, reason (text, required), granted_at, expires_at (granted + 4 h), reviewed_by,
reviewed_at, review_outcome (`appropriate`/`inappropriate`/`unclear`). **R**. Read audit events
during a grant carry the grant id.

## doctor_schedules and schedule_exceptions

**doctor_schedules:** staff (FK staff_members, must be a doctor with an active posting in the
department), facility, department, weekday (0–6), starts_at (time), ends_at (time), slot_minutes
(5–120), extra_bookings_allowed (0–20), valid_from, valid_until, is_active, version.
Check `ends_at > starts_at`. **I**.

**schedule_exceptions:** staff, date, kind (`leave`/`holiday`/`extra_session`), starts_at,
ends_at (null = whole day), reason, created_by. **I**.

## appointments

| Column | Type | Rules |
|---|---|---|
| patient_id, staff_id (doctor), facility_id, department_id | FK | |
| service_id | FK department_services | null (already built) |
| starts_at, ends_at | timestamptz | `ends_at > starts_at` |
| kind | varchar(12) | `new` / `follow_up` |
| source | varchar(12) | `front_desk` / `phone` / `walk_in` (portal later) |
| status | varchar(16) | part 03: `booked`, `checked_in`, `in_consultation`, `completed`, `cancelled`, `no_show` |
| token_number | int | null until check-in; `UNIQUE(staff, local_date, token_number)` |
| local_date | date | the appointment day in the facility time zone (for tokens and lists) |
| reason | varchar(200) | short, no detailed clinical text **[DR]** |
| is_extra | boolean | over the slot limit (D11) |
| rescheduled_from_id | FK appointments | null |
| cancel_reason, cancelled_by, cancelled_at | | |
| checked_in_at, booked_by | | |
| version | | |

**No double booking (database guarantee):** PostgreSQL exclusion constraint
`EXCLUDE USING gist (staff_id WITH =, tstzrange(starts_at, ends_at) WITH &&) WHERE (status IN
('booked','checked_in','in_consultation') AND NOT is_extra)` (needs `btree_gist`). Extra bookings
are counted per session in the service under a row lock.
Indexes: `(staff_id, local_date)`, `(patient_id, starts_at)`, `(facility_id, local_date, status)`.
Sensitivity: **C** (an appointment reveals that a person sees a given specialty).

## encounters

| Column | Type | Rules |
|---|---|---|
| patient_id, facility_id, department_id | FK | |
| attending_id | FK staff_members | responsible doctor |
| appointment_id | FK appointments | null for unbooked; `UNIQUE` when set |
| number | varchar(40) | visit number from scheme `encounter`; unique per organization |
| kind | varchar(16) | `outpatient` (Phase 3 adds `inpatient`, `emergency`, `day_care`…) |
| status | varchar(20) | part 03: `arrived`, `in_progress`, `finished`, `cancelled`, `entered_in_error` |
| chief_complaint | varchar(300) | |
| arrived_at, started_at, finished_at | timestamptz | |
| error_reason | text | when entered in error |
| version | | |

Indexes: `(patient_id, arrived_at DESC)` (chart timeline), `(facility_id, department_id, status)`
(active visits board), `(attending_id, arrived_at)`. **C**.

## Clinical tables (all **C**, all with `patient_id`, `recorded_by`, `recorded_at`, status incl. `entered_in_error` + `error_reason`; never deleted)

**vital_signs:** encounter (FK, required in Phase 2), kind (`bp_systolic`, `bp_diastolic`,
`pulse`, `temperature`, `resp_rate`, `spo2`, `height`, `weight`, `bmi`, `pain`), LOINC code,
value numeric(7,2), unit (UCUM: `mm[Hg]`, `/min`, `Cel`, `%`, `cm`, `kg`, `kg/m2`, `{score}`),
effective_at (when measured), abnormal (`low`/`high`/null), status (`final`/`entered_in_error`).
Index `(patient_id, kind, effective_at DESC)` (trends, last values).

**allergies:** patient, encounter (null), substance_text, category (`drug`/`food`/
`environment`/`other`), reactions (text), severity, status (`active`/`inactive`/`resolved`/
`entered_in_error`), verification (`unconfirmed`/`confirmed`/`refuted`), onset (date, null),
is_no_known_allergies (boolean: the explicit "NKA" entry), note, version. Check: an NKA entry has
no substance. A new active allergy ends an active NKA entry automatically.

**diagnoses:** patient, encounter, code_system (`icd10_who` / `icd10_cm` / `text`), code
(null for text), display (as shown when recorded, kept even if the catalogue changes),
free_text_reason (required for `text`), role (`primary`/`secondary`), certainty
(`working`/`provisional`/`final`), status (`active`/`resolved`/`entered_in_error`), onset, resolved_on,
version. Index `(patient_id, status)`.

**icd_codes (catalogue):** code_system, code, title, parent, is_billable (CM), version_label
(e.g. `ICD-10 2019`, `ICD-10-CM FY2027`), is_active. `UNIQUE(code_system, version_label, code)`.
Imported by a management command from the official files (part 05).

**clinical_notes:** patient, encounter, kind (`opd_consultation`, `triage`), author (FK users),
status (part 03: `draft`/`signed`/`amended`/`entered_in_error`), current_version (int),
signed_by, signed_at, version.

**clinical_note_versions:** note, number (1, 2, 3…), sections JSON (`complaint`, `history`,
`examination`, `assessment`, `plan`; a fixed shape validated by the service, the only JSON in
this design: spec 26.2 allows versioned document content), kind (`original`/`amendment`/
`addendum`), reason (required for amendment/addendum), author, created_at.
`UNIQUE(note, number)`. Append-only once the note is signed (database trigger, like the audit
log).

**reported_medications (D21):** patient, name_text, dose_text, frequency_text, since (date),
source, status (`active`/`stopped`/`entered_in_error`), recorded_by. Not orders.

## Lifecycle and retention

Nothing in these tables is ever deleted by a person; corrections use status changes,
amendments, "entered in error" and merges (spec 28.2). Retention periods: D24 (LEGAL). Drafts
are kept even if never signed. Merged patients keep their row (read-only).

## Migrations

All new tables (expand only); `CREATE EXTENSION pg_trgm` and `btree_gist` in the first migration
(both available on Amazon RDS for PostgreSQL). ICD catalogues loaded by command, not migrations.
Numbering schemes `mrn` and `encounter` already exist for every hospital.
