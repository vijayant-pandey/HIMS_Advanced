# Data design: hospital numbering schemes (HIMS-ORG-003)

Part of **Artifact A — Detailed Data Architecture** (spec 28). P0-B database design for business
numbers. The domains that use these numbers (patients, encounters, billing, claims) arrive in
Phases 2–5 and call the service described in §4.

**Spec:** 4.1 ("hospital-specific numbering schemes for patient IDs, encounters, invoices and
claims"), 4.5 ("MRN is a hospital-facing identifier and should not be the primary database key"),
10 (concurrency), 28.2 ("explicit business identifiers… separately from database keys"; "make
uniqueness rules explicit; never assume an MRN is globally unique across deployments").

## 1. What a number looks like

```text
[prefix] [facility code] [period] [zero-padded running number], joined by a separator

MRN-00000123          MRN, never restarts, 8 digits
ENC-2026-0000007      visit, restarts every calendar year
INV/26-27/000042      India GST invoice, restarts every financial year (April), short year
ENC-BLR-2026-0000001  with the facility code
```

| Setting | Values | Notes |
|---|---|---|
| Prefix | 0–10 capital letters/digits | e.g. MRN, UHID, INV |
| Separator | `-`, `/` or none | GST allows only letters, digits, `-` and `/` |
| Include facility code | yes/no | the code of the facility where the number is issued |
| Restarts (period) | never, calendar year, financial year, month | starts the running number again |
| Year format | full (2026, 2026-27) or short (26, 26-27) | display only; the counter key is always full |
| Financial year starts | month 1–12 | India 4 (April); US hospitals choose their fiscal year |
| Digits | 3–12 | zero padding; numbers grow past it rather than fail |
| Each series starts at | ≥ 0 | first running number of each new period |

Dates use the facility's time zone (else the hospital's default), so an invoice issued at
00:30 on 1 April in India belongs to the new financial year.

## 2. Tables

### numbering_schemes
`id` UUID · `organization_id` · `document_type` (`mrn`, `encounter`, `invoice`, `claim`) ·
`facility_id` NULL = whole hospital · the settings above · `is_active` · `version` · timestamps.

* **Unique** `(document_type, facility_id)` with `NULLS NOT DISTINCT` (PostgreSQL 15+): one
  hospital-wide scheme and at most one per facility for each type.
* **Check** `numbering_mrn_hospital_wide`: an MRN scheme has no facility. A patient keeps one MRN
  in every branch of the hospital.
* **Check** padding 3–12, financial-year month 1–12.
* **India invoices:** the longest possible number must be ≤ 16 characters (GST, CGST Rules
  rule 46(b)). Checked in the model, so the app, API and admin console all refuse it.

### numbering_counters
`scheme_id` · `period_key` (`""`, `2026`, `2026-27`, `202610`) · `last_value` · `updated_at`.
**Unique** `(scheme_id, period_key)`. One row per scheme and period, created on first use.

### issued_numbers (register, append-only)
`id` UUID · `organization_id` · `scheme_id` · `document_type` · `facility_id` · `value` ·
`period_key` · `sequence` · `issued_by` · `reference` (e.g. `patient:<uuid>`, never names) ·
`created_at`. **Unique** `(document_type, value)`: the database refuses a duplicate number even
if application code were wrong. Index `(document_type, created_at DESC)` for the register view.

## 3. Which scheme applies

1. The facility's own **active** scheme for that type, if there is one (not for MRN).
2. Otherwise the hospital-wide active scheme.
3. Otherwise `409 NUMBERING_NOT_CONFIGURED` ("Set one up on the Numbering page").

Facility series are useful in India when branches are in different states, since each GST
registration (GSTIN) needs its own invoice series.

## 4. Issuing a number (concurrency, spec 10)

`apps.numbering.services.issue_number(document_type, facility, actor, reference)` is called
**inside the transaction that creates the record** (patient, encounter, invoice, claim):

1. Find the scheme (§3) and the period key for today in the facility's time zone.
2. Insert the counter row if missing (`INSERT … ON CONFLICT DO NOTHING`), then lock it with
   `SELECT … FOR UPDATE`.
3. Take the next running number. If its formatted value was already issued (possible only after a
   format change, e.g. prefix A → B → A), skip to the next free one.
4. Save the counter and write the register row. The lock is held until the caller commits.

Results:
* **No duplicates.** Simultaneous requests wait for each other (tested with 6 threads × 5
  numbers: 30 unique, consecutive numbers). The unique index is a second guard.
* **No gaps.** If the record fails and its transaction rolls back, the counter rolls back too,
  so the next record reuses that number. GST invoice series must be continuous. This is why a
  locked row is used and not a PostgreSQL sequence, which leaves gaps.
* Trade-off: numbers of one type in one facility are issued one at a time. This is fine at
  hospital volumes. The lock is held only for the caller's short transaction.

## 5. Changing settings

* Settings can change at any time (audited with before/after values). Numbers already issued
  never change. New settings apply from the next number.
* **Number type and facility cannot change** after creation. Create a new scheme instead.
* **Continue from a previous system:** "next running number" can be set, for example to 54322
  when the old software's last MRN was 54321. It **only moves forward**
  (`409 NUMBER_WOULD_GO_BACKWARDS`), so a number is never handed out twice. Audited as
  `numbering.next_number.set`.
* Deactivating a facility scheme sends that facility back to the hospital-wide series.
  Deactivating a hospital-wide scheme stops numbers of that type until one is active again
  (the screen warns about this).

## 6. Defaults

Every hospital gets four hospital-wide schemes: at provisioning, and on the next `migrate` for
hospitals provisioned earlier. They are created only if missing, so your own changes are never
overwritten.

| Type | India | US |
|---|---|---|
| MRN | `MRN-00000001` | `MRN-00000001` |
| Encounter | `ENC-2026-0000001` (calendar year) | `ENC-2026-0000001` |
| Invoice | `INV/26-27/000001` (financial year from April; 16 chars) | `INV-2026-0000001` |
| Claim | `CLM-2026-27-000001` (financial year) | `CLM-2026-0000001` |

## 7. Permissions and audit

| Permission | Who has it | Two-factor |
|---|---|---|
| `numbering.view` | Organization administrator; Facility administrator | no |
| `numbering.manage` | Organization administrator (hospital-wide and every facility); Facility administrator (own facility's series only) | **yes** (affects legal invoice series) |

Hospital-wide schemes are visible to anyone with `numbering.view`. Audit actions:
`numbering.scheme.created`, `numbering.scheme.updated`, `numbering.next_number.set`. The register
itself records every issued number (who, when, for what).

## 8. API and screens

| Endpoint | Permission |
|---|---|
| `GET /api/v1/numbering-schemes/` (`?document_type=`) · `GET /numbering-schemes/{id}/` | view |
| `POST /numbering-schemes/` (Idempotency-Key) · `PATCH /numbering-schemes/{id}/` (version) | manage |
| `POST /numbering-schemes/preview/`: example and problems for unsaved settings | view |
| `POST /numbering-schemes/{id}/next-number/`: continue from a previous system | manage |
| `GET /issued-numbers/` (`?document_type=`, `?facility=`, `?value=`) | view |

* **App:** Numbering page (menu → Numbering). Shows every type with its next number, an edit form
  with a live preview, "Continue from…", facility series and the issued-number register.
* **Admin console:** Numbering schemes (all settings, example and next number, "Set next running
  number"), Number counters and Issued numbers (read-only).

## 9. Retention

Schemes and counters are configuration. Issued numbers are kept for as long as the records they
identify (financial records: country retention rules, spec 36, 🔒 LEGAL). Nothing here contains
patient data.
