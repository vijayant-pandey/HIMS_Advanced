# Artifact A: data architecture (spec 28)

The detailed data architecture of HIMS, versioned with the code (spec 28). It covers everything
built so far (Phase 1: hospital set-up, staff, access, audit and platform). Patient, clinical and
financial domains are added here as they are built.

**Start here:**

| Document | What it holds | Kept up to date by |
|---|---|---|
| [data-dictionary.md](data-dictionary.md) | Every table and column: type, empty allowed, default, allowed values, who sets it, sensitivity, meaning; keys, constraints, indexes, lifecycle and owner per table | **Generated** from the models (`python manage.py data_dictionary`); CI fails when it is stale |
| [erd.md](erd.md) | ERDs: all tables with relationships, and one diagram per domain with columns | **Generated** (same command) |
| This page | The rules behind the tables: ownership, classification and access, lifecycle, transactions, history, migrations, catalogs, data flows, test data | By hand, with each change |
| Domain designs | [Facilities and departments](facilities-and-departments.md) · [Locations and beds](locations-and-beds.md) · [Numbering](numbering-schemes.md) · [Access reviews](access-reviews.md) · [Cover arrangements](cover-arrangements.md) · [Rotas and leave](rotas-and-leave.md) · [Audit integrity](audit-integrity.md) | By hand, per feature |

## Spec 28.1 deliverables

| # | Deliverable | Where | Status |
|---|---|---|---|
| 1 | Domain-by-domain logical ERD | [erd.md](erd.md), one diagram per domain | ✅ built domains |
| 2 | Physical ERD, all tables and cardinalities | [erd.md](erd.md), "All tables" | ✅ |
| 3 | Data dictionary (type, nullability, default, allowed values, source, sensitivity) | [data-dictionary.md](data-dictionary.md) | ✅ |
| 4 | Index and uniqueness specification tied to query patterns | Per table in the dictionary; patterns in [section 4](#4-indexes-and-the-queries-they-serve) | ✅ checked at production-like volume ([volume check](volume-check.md), HIMS-DATA-002) |
| 5 | Lifecycle, retention, archive and correction rules | "Lifecycle" per table in the dictionary; [section 3](#3-lifecycle-and-correction) | ✅ (purge of housekeeping tables by periods the hospital sets, with legal hold: HIMS-COMP-006) |
| 6 | Transaction boundaries and concurrency rules | [section 5](#5-transactions-and-concurrency) | ✅ |
| 7 | Data classification and access matrix | "Sensitivity" per column; [section 2](#2-classification-and-access) | ✅ |
| 8 | Historical/version model for clinical and financial facts | [section 6](#6-history-and-versions) | 🟡 rules set; clinical/financial tables come with Phases 2–5 |
| 9 | Migration and backfill playbook | [section 7](#7-migrations-and-backfills) and [database-migrations.md](../../workflows/database-migrations.md) | ✅ (release job HIMS-OPS-006: 🔒 AWS) |
| 10 | Terminology/catalog ownership and update process | [section 8](#8-catalogs-and-terminology) | ✅ for staff catalogs; clinical code systems 🔒 CLIN |
| 11 | Data-flow lineage to external providers and analytics | [section 9](#9-data-flows) | ✅ (no external providers yet) |
| 12 | Seed and synthetic data strategy | [section 10](#10-seed-and-synthetic-data) | ✅ |

Acceptance (spec 28.8) is reached for the built Phase 1 domains. It must be repeated for each
**P0 domain** (patients/MPI first) before that domain is released: HIMS-DATA-003.

## 1. Ownership (spec 28.3)

Each domain section of the [dictionary](data-dictionary.md) names its owner. The rules:

- One owner writes each table, through its `services.py`. Other domains read it or call those
  services, never write it directly. The admin console uses the same services.
- Hospital configuration (organization, facilities, departments, locations, numbering, features)
  belongs to the organization/facility domain. Changes are permission-checked and audited.
- Staff credentials belong to the staff domain. Verification and expiry are separate from the
  person's sign-in account (`users`), which belongs to the identity domain.
- Access (roles, assignments, reviews, cover) belongs to identity and access. Lent cover access
  is ordinary `role_assignments` rows linked to `access_delegations`.
- The audit log is its own security boundary. No other domain reads it; only auditors do.
- Bed **status** is maintained by the bed domain now; bed **occupancy** will be derived from
  admission/bed-assignment events (Phase 3) and never edited by hand.
- No foreign keys cross hospital deployments: each hospital has its own database (ADR-003).

## 2. Classification and access

Every column has a sensitivity level in the [dictionary](data-dictionary.md). Rules live in
`backend/common/datadict/catalog.py`; a test makes sure credentials are **Secret** and personal
data is **Restricted**.

| Level | Examples | Handling |
|---|---|---|
| **Secret** | password hash, two-factor secret (encrypted), backup-code hashes, session keys | Never shown, exported, logged or traced. Encrypted or hashed at rest. |
| **Restricted** | names, emails, employee and registration numbers, documents, IP addresses, audit content | Shown only to people whose permission covers that record and place. Kept out of logs, traces, URLs and emails (except the person's own). |
| **Internal** | hospital configuration, catalogs, references, system metadata | Shown to staff with the matching view permission. |
| **Clinical (PHI)** | none yet: patient data from Phase 2 | Stricter rules (minimum necessary, read auditing, break-glass) decided with the P0 documents. |

**Who can read what (system roles; custom roles combine these permissions).** Staff are "in" a
facility or department through a current posting ([staff visibility](../../workflows/staff-visibility.md)):

| Data | Org admin | Facility admin | HR / credentialing | Head of department | Bed manager | Basic staff | Auditor |
|---|---|---|---|---|---|---|---|
| Hospital, facilities, departments | ✅ change | change, own facility | view | view, own department | view facilities | view | — |
| Locations and beds | ✅ change | change, own facility | — | view, own department | view; change bed status | view | — |
| Equipment register (HIMS-FAC-009) | ✅ change | change, own facility | — | view, own department | — | — | — |
| Message wording (HIMS-NOTIF-003) | ✅ change | — | — | — | — | — | — |
| Numbering, feature settings | ✅ change | change, own facility | — | — | — | — | — |
| Staff, qualifications, licences, catalogs (Restricted) | ✅ change | view, staff posted at own facility | ✅ change and verify | view, staff posted in own department | — | — | — |
| Staff documents: licence and certificate copies (Restricted) | ✅ open | — | ✅ open | — | — | — | — |
| Clinical privileges (Restricted notes; HIMS-STAFF-016) | ✅ give and end | view, staff posted at own facility | ✅ give and end | view, staff posted in own department | — | — | — |
| Rotas: shifts, on-call (Restricted: who is away, not why) | ✅ plan | — | view | plan, own department | — | view | — |
| Minimum staffing (HIMS-STAFF-015) | ✅ set | — | view | set, own department | — | view | — |
| Leave requests incl. kind of leave (Restricted) | ✅ decide | — | ✅ decide and record | decide, own department (never their own) | — | own only | — |
| Leave balances and entitlements (Restricted; HIMS-STAFF-013) | ✅ set and adjust | — | ✅ set and adjust | view balances, own department | — | own only | — |
| Accounts, roles, access, cover (Restricted) | ✅ change | — | — | — | — | — | — |
| Access reviews | ✅ decide | — | — | — | — | — | read and download |
| Audit log and integrity (Restricted) | **no** (separation of duties) | — | — | — | — | — | ✅ read |
| Backups and restore drill evidence (counts and fingerprints, no record contents) | ✅ make backups, run drills | — | — | — | — | — | ✅ read |

**Below the app, in the database itself** ([separate database users](../../workflows/database-users.md),
HIMS-OPS-007): the app's own database user can read and write rows but only *add* to the audit log and
other evidence tables (never change, delete or empty them) and owns nothing; a read-only user for
reports reads every table except the **Secret** columns above; only the owner, used by `migrate`,
can change the structure.
| Secret columns | nobody | nobody | nobody | nobody | nobody | nobody | nobody |

The exact permissions per role are in `backend/apps/access_control/catalog.py` and
[Hospital_Departments_and_Doctors_RBAC.MD](../../status/Hospital_Departments_and_Doctors_RBAC.MD).
Every person also sees their own account, sign-ins and cover arrangements.

## 3. Lifecycle and correction

- **Nothing is deleted by people.** Records are switched off (`is_active`), revoked
  (`revoked_at` + reason), ended (`valid_until`, `left_on`), archived (staff documents) or
  change status, and the change is audited. The admin console has no delete buttons.
- **Append-only tables** (database triggers refuse UPDATE/DELETE): `audit_events`,
  `audit_chain_entries`, `audit_integrity_checks`. `issued_numbers` is append-only by service.
- **The only physical deletions:** department opening-hour rows (replaced as a set, audited),
  two-factor devices and backup codes on reset (audited), expired idempotency records (after 48
  hours) and expired browser sessions.
- **Corrections:** a wrong value is changed through the normal screen with a version check, and
  the before/after values are kept in the audit log. Signed clinical and financial facts will use
  amendments and reversals instead (section 6).
- **Retention periods** for audit and personal data are a legal decision (🔒 LEGAL, ADR-013).
  Until then nothing is purged except the technical records listed above.
- **Retention purge (HIMS-COMP-006, 2026-11-10):** the hospital sets periods for six housekeeping tables (`user_sessions`, `notifications`, `user_invitations`, `user_password_resets`, `browser_security_reports`, `console_access_blocks`); nothing goes until a period is set, shorter periods wait 7 days, legal holds win, and each run is kept in `retention_purge_runs` (append-only). Each table's "Lifecycle" in the dictionary says what goes. The audit log is not purged (HIMS-COMP-007). [How-to](../../workflows/retention-purge.md).

## 4. Indexes and the queries they serve

Validated with production-like synthetic volume and query plans (spec 28.6; HIMS-DATA-002,
2026-11-10): `python manage.py volume_check` fills a throw-away copy with the records of a 500-bed
hospital (3.6 million rows), reads PostgreSQL's plan for every query below and fails if one does not
use its index or takes over 100 ms. The list of queries lives in `apps/performance/queries.py`; a
test keeps it and this table in step. Results: [volume check](volume-check.md). Foreign keys are
always indexed.

| Query | Index or unique rule |
|---|---|
| Audit events by person, by record, by event type, by time | `audit_actor_idx`, `audit_resource_idx`, `audit_action_idx`, `audit_occurred_idx` |
| A person's current access (every request) | `role_assignment_user_idx` (user, revoked_at); one active grant per user/role/place (`role_assignment_active_unique`) |
| Cover a person gives or gets, current first | `access_deleg_delegate_idx`, `access_deleg_delegator_idx` |
| A person's open sign-ins ("My sign-ins") | `user_session_open_idx` (user, ended_at) |
| Password-reset rate limit (per person per hour) | `password_reset_user_idx` (user, created_at) |
| Bed board by facility, ward and status; free beds of a type | `beds_board_idx`, `beds_type_idx` |
| Wards of a type in a facility | `wards_type_idx` |
| Licences expiring soon (daily alerts) | `staff_credential_expiry_idx` |
| Numbers issued per document type, newest first | `issued_numbers_type_idx` |
| Outbox events waiting to be sent | `outbox_pending_idx` (partial: pending only) |
| Failed and dismissed outbox events (health page counts, clean-up) | `outbox_attention_idx` (partial: dead and dismissed only; added by HIMS-DATA-002) |
| Old published outbox events (daily clean-up) | `outbox_published_idx` (partial: published only) |
| Failed messages due to be sent again (background job) | `notification_retry_idx` |
| Messages screen, newest first | `notification_created_idx` |
| The current browser's sign-in (every sign-in check) | unique `session_key` |
| Rota: one department's week, one person's week | `shift_department_day_idx`, `shift_staff_day_idx` |
| Expired idempotency records (hourly purge) | `idempotency_expiry_idx` |
| Retention purge: ended sign-ins and messages older than the cut-off | `user_session_ended_idx` (partial: ended only; added by HIMS-DATA-002, which found `user_session_open_idx` could not serve it), `notification_created_idx` (batches are taken in no particular order so this index can be used) |
| Integrity check history | `audit_check_finished_idx` |
| Audit sealing: the next events to seal (every minute); events waiting (integrity status) | `audit_occurred_idx` with `audit_chain_entries_event_id_key`, written as NOT EXISTS (HIMS-DATA-002 found the join form reading the whole chain on every batch: 2.9 s at 1.3 million links, now 0.09 s) |
| Codes unique within their scope (facility, department, ward, room, bed, role, catalog) | unique constraints listed per table in the dictionary |

Patient search, encounter, medication, lab and claim indexes (spec 28.6) are designed with
their domains.

## 5. Transactions and concurrency

- **One transaction per business action**, opened by the domain service
  (`transaction.atomic`), never by the web request (`ATOMIC_REQUESTS` is off). The audit event
  is written in the same transaction, so a change and its audit record commit or roll back
  together. Refusals ("access denied") are audited after the rollback.
- **Editable configuration carries a `version`.** The service locks the row
  (`SELECT … FOR UPDATE`) and compares the version the person saw; a stale save gets 409
  "This record changed since you loaded it".
- **Retries are safe:** create requests accept an `Idempotency-Key`; replays return the first
  answer (`idempotency_records`).
- **Messages to other systems** are written to `outbox_events` in the same transaction and sent
  afterwards (ADR-005/012), so nothing is sent for a change that rolled back.
- **Numbers never collide or skip:** counters are locked per scheme and period
  (`numbering_counters`); tested with parallel requests.
- **One at a time where it matters:** audit sealing and checks use PostgreSQL advisory locks;
  one open access review at a time (partial unique index).

## 6. History and versions

- **Configuration:** the current row plus the full before/after history in the audit log, which
  is tamper-evident (hash chain, `audit_integrity.md`).
- **Access:** never overwritten; every grant, revocation, review decision and cover arrangement
  stays as its own row with who/when/why.
- **Clinical facts (Phase 2+, spec 28.5):** notes and reports keep author, signer, timestamps,
  state and version; a correction creates a new version or linked amendment with a reason, never
  an overwrite. Observations keep effective time, recorded time, source, unit, status and
  correction history.
- **Financial facts (Phase 5, spec 28.4):** charges, invoices, claims, submissions, remittances,
  payments and allocations as separate records; corrections by reversal entries, never by
  editing a posted amount. Money in decimal with explicit currency.

## 7. Migrations and backfills

Follow spec 28.7 and [database-migrations.md](../../workflows/database-migrations.md):

- Migrations are generated in development, reviewed in the PR, and CI fails if one is missing
  (`makemigrations --check`).
- Every hospital database is migrated after a merge (India, then US); the runbook shows how to
  check which migrations each one has.
- Changes are additive first (new nullable column or table, then code, then clean-up later:
  expand and contract). Constraints that existing data might break are checked first.
- After a model change, regenerate the dictionary (`python manage.py data_dictionary`); CI fails
  otherwise.
- Backfills run as management commands that can be re-run safely (idempotent), report progress,
  and work in batches. Risky data changes need a verified backup first.
- Hosted environments: a dedicated migration release job with a lock, and the schema version
  recorded per hospital (HIMS-OPS-006, 🔒 AWS).

## 8. Catalogs and terminology

| Catalog | Owner | How it changes |
|---|---|---|
| Permissions | Code (`access_control/catalog.py`) | Code change + PR; synced on migrate; removed codes deactivated |
| System roles | Code (`SYSTEM_ROLES`) | Code change + PR; synced on migrate |
| Custom roles | Hospital administrators | Access page / admin console, versioned and audited |
| Job titles, specialties, qualification types | Shipped defaults + hospital additions | **Job titles & catalogs** page (`staff.catalogs.manage`); switched off, never deleted; India/US defaults by country |
| Feature catalog | Code (`features`) | Code change; per-hospital and per-facility settings in the app |
| Audit event names | Code (`audit/catalog.py`) | Every event needs a plain-language label (test-enforced) |
| Clinical code systems (ICD, SNOMED CT, LOINC, drug codes) | Clinical governance | 🔒 CLIN / VENDOR: chosen with the clinical P0 documents; source and version stored with each coded value (spec 28.2) |

## 9. Data flows

| Flow | Data | Where it goes | Safeguards |
|---|---|---|---|
| Emails (invitations, password reset, two-factor notices, expiry alerts, review reminders, cover notices, integrity alerts) | Names, dates, links; never clinical data or passwords | Email service (console on developer PCs) | Links are single-use and expire; only the person concerned or the responsible role receives them |
| Staff documents | Uploaded files (Restricted) | Hospital's own storage folder; S3 later (HIMS-OPS-015) | No public links; permission-checked, audited downloads |
| Traces and logs | Technical timings, ids, reference numbers | Console or OTLP collector when switched on (ADR-021) | No query strings, SQL values, bodies or secrets |
| CSV downloads (audit log, access reviews) | Restricted | The auditor's or reviewer's computer | Permission-checked, audited, spreadsheet-formula safe |
| External providers (payers, labs, PACS, ABDM, analytics) | none yet | — | Each will get a lineage entry here and an ADR before it is built (spec 7, 29) |

## 10. Seed and synthetic data

- **Never real patient or staff data** outside a hospital's own production database (spec 31.1).
- A new hospital database gets its reference catalogs from migrations (specialties,
  qualification types, job titles for India and the US) and the permission catalog on migrate.
  `manage.py provision_organization` then creates the organization, system roles, numbering
  schemes, hospital-wide feature settings, the first administrator and (optionally) the first
  auditor. Nothing else is seeded.
- Tests build their own synthetic people and places (`backend/conftest.py`), with names like
  "Synthetic Admin" and `@synthetic.test` addresses. Test passwords follow the
  `Synthetic-<Word>-Passw0rd-NNNN` pattern so the secret scanner can tell them apart.
- End-to-end checks run against throw-away databases created for the run.
- The manual test guide ([flow-part1.md](../../testing/flow-part1.md)) uses invented people
  (Ravi Doctor, Asha Nurse) and `@test.local` addresses.
- Volume testing (HIMS-DATA-002) generates synthetic rows at production-like scale with the
  same rules, only into the throw-away database `hims_volume` (`seed_volume_data` refuses any
  other): "Synthetic Staff 000123", `@synthetic.test`, passwords that cannot be used. See
  [volume check](volume-check.md).
