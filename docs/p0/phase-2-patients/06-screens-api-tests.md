# 06 Screens, API contracts, acceptance tests and build plan (P0-I)

DRAFT.

## 1. Screens (sketches)

**Front desk: Patients**
```
┌ Patients ─────────────────────────────────────────────── [Register new patient] ┐
│ Search: [ MRN, phone, ID number or name (+ age)          ]  [Search]              │
│ Name             MRN        Age/Sex  Phone   Last visit                           │
│ Asha Nurse       IN-000123  34 F     …4821   12 Oct · Cardiology   [Open] [Book]  │
└───────────────────────────────────────────────────────────────────────────────────┘
```
**Register:** form in three blocks (Person · Contact · People and IDs) → Save → if likely
duplicates: "These patients look similar: [Open] … or ☐ This is a different person, reason …".

**Patient chart**
```
┌ ASHA NURSE · IN-000123 · 34 F · ⚠ Allergy: Penicillin (severe)        [Book] [Visit] ┐
│ Overview | Visits | Notes | Vitals | Demographics | Audit                             │
│ Problems: Hypertension (I10)   Medicines (reported): Amlodipine 5 mg daily            │
│ Last vitals 12 Oct: BP 152/94 ▲  Pulse 78  SpO₂ 98%   Next: 26 Oct 10:20 Dr Ravi      │
└───────────────────────────────────────────────────────────────────────────────────────┘
```
**Appointments (calendar):** department → doctor → day view with slots (free / booked / extra),
book from a slot; week view for schedules.

**OPD queue (today):** per doctor: token, patient, status (waiting / with doctor / done / no-show),
time waiting; buttons Check in, Walk in, Call next.

**Doctor: My patients today** → **Consultation screen**: left = header + history; right = Vitals ·
Allergies · Diagnoses (ICD search) · Note (5 sections, autosave draft, Sign) · Finish visit.

**Medical records:** Possible duplicates · Merge (side by side) · Merges to approve · Emergency
access to review · Unsigned notes report.

All new screens: accessibility check in the browser tests, keyboard use, no clinical data in
URLs (ids only).

## 2. API (all under `/api/v1/`, permission per part 04, errors as RFC 9457 with reference)

| Method and path | What | Idempotency / concurrency |
|---|---|---|
| `GET /patients/?q=` | Search (minimal fields) | audited |
| `POST /patients/` | Register (+ duplicate check; `409 POSSIBLE_DUPLICATE` with candidates unless `override_reason`) | Idempotency-Key |
| `GET /patients/{id}/` | Chart header + demographics (clinical parts only in scope) | audited |
| `PATCH /patients/{id}/` | Edit demographics | version |
| `…/contacts/`, `…/relationships/`, `…/identifiers/`, `…/consents/` | Sub-records | version / append |
| `GET /patient-duplicates/` · `POST /patient-merges/` · `POST /patient-merges/{id}/approve/` `…/reject/` `…/undo/` `…/approve-undo/` | Duplicates and merges | version; two-person check |
| `POST /patients/{id}/emergency-access/` | Break-glass | reason |
| `GET/POST /doctor-schedules/`, `/schedule-exceptions/` | Sessions | version |
| `GET /appointments/?doctor=&date=` · `GET /availability/?doctor=&date=` | Calendar, free slots | — |
| `POST /appointments/` | Book (`409 SLOT_TAKEN`) | Idempotency-Key; exclusion constraint |
| `POST /appointments/{id}/reschedule/` `cancel/` `check-in/` `no-show/` `undo-no-show/` | Lifecycle | version |
| `POST /walk-ins/` | Walk-in: appointment + encounter + token | Idempotency-Key |
| `GET /opd-queue/?facility=&date=` | Queue | — |
| `GET /encounters/{id}/` · `POST /encounters/{id}/start/` `finish/` `reopen/` `entered-in-error/` | Visit lifecycle | version |
| `POST /encounters/{id}/vitals/` · `POST /vitals/{id}/entered-in-error/` | Vitals | Idempotency-Key |
| `GET/POST /patients/{id}/allergies/` · `PATCH /allergies/{id}/` | Allergies | version |
| `GET /icd-codes/?q=` · `POST /encounters/{id}/diagnoses/` · `PATCH /diagnoses/{id}/` | Diagnoses | version |
| `POST /encounters/{id}/notes/` · `PATCH /notes/{id}/` (draft) · `POST /notes/{id}/sign/` `amend/` `addendum/` `entered-in-error/` | Notes | version; signed versions immutable |
| `GET/POST /patients/{id}/reported-medications/` | Reported medicines | version |
| `GET /reports/opd-daily/` · `GET /encounters/{id}/summary.pdf` | Reports | audited |

Every write: permission check, scope check (patient-level rule), domain action, version check,
audit event, outbox event where listed in part 03, OpenAPI documented, frontend types generated.

## 3. Acceptance tests (minimum, spec 26.1 #10)

**Positive:** register with age only → MRN issued, DOB estimated · search by MRN/phone/similar
name · book, check in, consult, sign, finish · walk-in gets next token · vitals with abnormal flag
· allergy shows in header · ICD diagnosis saved with code and display · amend signed note keeps
both versions · merge moves everything, old MRN still finds patient · undo merge.

**Negative:** register without name/sex/age → field errors · same ABHA on two patients → blocked
· double-booking same slot (parallel requests) → one wins · book in the past / outside session →
refused · sign someone else's draft → refused · edit signed note → refused · merge approved by
requester → refused · vitals 400 kg → refused · finish visit with unsigned note → refused.

**Boundary:** DOB today; age 0 months; 130 years; slot at session end; token numbers restart each
day; 30th day of merge undo; 4 h emergency access expiry.

**Permissions:** receptionist cannot open clinical tabs · doctor outside department sees
demographics only and is offered emergency access · admin has no clinical view · auditor sees
"who opened" but not charts · restricted record hidden from search.

**Failure:** MRN scheme missing → nothing saved · email provider down → appointment still booked,
reminder retried · two tabs editing a note → second save refused · network retry on register →
one patient.

**Privacy:** no clinical text or names in logs, traces, URLs, emails (except the patient's own
reminder: date, time, doctor, hospital; no diagnosis).

**Browser (Playwright):** full OPD day: register → book → check in → vitals → consult → sign →
finish → visit summary; accessibility on every new screen.

## 4. Build plan after sign-off

| Slice | Content | Ships with |
|---|---|---|
| **2A** Registration and search | patients app, identifiers, contacts, relationships, consents, duplicate check, search, chart header, roles Receptionist and Medical records, read auditing | Admin console, data dictionary, tests |
| **2B** Scheduling and OPD | schedules, exceptions, appointments (no double booking), walk-ins, tokens, queue, no-show job, email confirmations/reminders (needs the notification service, built first) | Doctor and Scheduler roles |
| **2C** Visit and clinical recording | encounters, vitals, allergies, ICD catalogues + import command, diagnoses, notes with sign/amend, reported medicines, consultation screen, emergency access, OPD nurse role | Clinical (PHI) sensitivity level |
| **2D** Merge and reports | duplicates list, two-person merge and undo, visit summary PDF, OPD daily list, unsigned-notes report, emergency-access review | Phase 2 exit check (spec 20) |

Each slice is its own PR with backend, database, screens, admin console, tests (unit, API,
browser + accessibility), docs and tracker updates, and a migrate step.

Prerequisites not blocked: notification service (email), bed board is independent. Blocked for
**go-live with real patients** (not for building): legal items (part 05), hosting (AWS), SMS
vendor for SMS reminders.
