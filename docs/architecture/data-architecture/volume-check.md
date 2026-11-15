# Volume check: indexes and response times at hospital size (HIMS-DATA-002, HIMS-OPS-017)

Spec 28.6: "Validate indexes with production-like data volume and query plans." Spec 18: "p95
below 300–500 ms for ordinary reads under expected load." How to run it:
[performance checks](../../workflows/performance-checks.md). Why it works this way:
[ADR-031](../../decisions/ADR-031-performance-targets-and-volume-check.md).

## The size used (scale 1)

A **500-bed hospital**, sized from common ratios. The numbers are estimates to confirm with the
first hospitals; `--scale` multiplies all of them.

| Table | Rows | How the number was reached |
|---|---|---|
| Staff (`users`, `staff_members`) | 2,000 | About 4 staff per bed in Indian private hospitals |
| Licences (`staff_credentials`) | 2,000 | One registration per person; expiry dates spread over three years |
| Beds (`beds`) | 1,500 | 50 wards × 10 rooms × 3 beds (bed counts include day-care and observation beds) |
| Rota (`shifts`) | 120,000 | Everyone on one shift a day for 60 days (30 past, 30 ahead) |
| Audit log (`audit_events`) | 2,000,000 | Phase 2 adds 20–50 read events per patient visit (P0 roles document); at about 1,500 visits a day that is roughly 45,000 events a day, so 2 million is about **six weeks of Phase 2 use**, or **several years of Phase 1 use** |
| Sign-ins (`user_sessions`) | 300,000 | 2,000 people signing in about once on each working day for a year (the retention minimum is 365 days) |
| Messages (`notifications`) | 300,000 | Invitations, resets, alerts and, from Phase 2, patient messages for a year |
| Background events (`outbox_events`) | 500,000 | 45 days of events: more than the 30 days the clean-up keeps, so the clean-up has work to do |
| Repeated-request records (`idempotency_records`) | 50,000 | What the hourly clean-up leaves: about 49 hours of changes |
| Issued numbers (`issued_numbers`) | 300,000 | Medical record and encounter numbers for a year |
| Password resets (`user_password_resets`) | 10,000 | Closed requests over a year |
| Access (`role_assignments`) | 200 | One in ten staff given an administrative role (clinical roles come with Phase 2) |

Total: about **3.6 million rows**. Spread over a year so that date searches ("one day", "older than
the cut-off") find realistic amounts. The copy's audit log is sealed into the tamper-evident chain
before measuring, as the every-minute job keeps a hospital's log sealed.

Phase 2 tables (patients, encounters, orders, results) are sized and checked the same way when they
are built (HIMS-DATA-003). At `--scale 10` the audit log holds 20 million events, about a year of
Phase 2 use.

**Since HIMS-DATA-003 (2026-11-14)** the patient register is in the copy too (rows below), and the
audit log's 2 million events are 1.5 million of the Phase 1 kinds plus 500,000 patient events
(records opened, searches, histories). Total: about **5.9 million rows**.

| Table | Rows | How the number was reached |
|---|---|---|
| Patients (`patients`) | 500,000 | About 150,000 new patients a year at a 500-bed hospital: a little over three years. Names are made of syllables that belong to nobody; a few family names are very common (the commonest: 1 patient in 17), as Kumar or Devi are |
| Contacts (`patient_contacts`) | 800,000 | A mobile each (one family in five shares one), an address for 6 in 10 |
| ID numbers (`patient_identifiers`) | 300,000 | 6 patients in 10 give one (Aadhaar in India, SSN in the US), stored as fingerprints |
| Consent decisions (`patient_consents`) | 650,000 | The privacy notice for everyone, an SMS decision for 3 in 10 |
| Relatives (`patient_relationships`) | 100,000 | 1 patient in 5 |
| Earlier names and MRNs (`patient_aliases`) | 10,000 | 1 in 50; one in five of them an earlier MRN after a merge |
| Restricted records | 500 | 1 in 1,000 (VIP) |
| Emergency access (`patient_emergency_access`) | 2,000 | To the restricted records; 19 in 20 reviewed |
| Patient audit events (in `audit_events`) | 500,000 | Records opened (7 in 10; restricted openings marked), searches, histories |

## Results on a developer PC (2026-11-10, scale 1, 20 calls per screen)

PostgreSQL 17, Windows 11 developer laptop, the copy built, sealed and removed by `volume_check`.
Times are the database's own execution time (queries) and p95 in-process (screens); hosted times
will add the network.

### What the first runs found, and the fixes

| Found | At hospital size | Fix | After |
|---|---|---|---|
| Retention purge's "sign-ins ended before the cut-off" had no index | 67 ms, whole table read | `user_session_ended_idx` (built `CONCURRENTLY`) | 0.2 ms |
| Background jobs: "failed events" count read the whole outbox | 159 ms per count, page p95 267 ms | `outbox_attention_idx` (dead and dismissed only; `CONCURRENTLY`) | 1.8 ms; page p95 21 ms |
| Retention purge batches asked for id order, so the date index could not be used | 33 ms, whole table walked | batches taken in no particular order (`retention.batch_ids`) | 2.8 ms |
| Audit log: the total count grew with the log | p95 366 ms at 2 million (would pass 3 s at 20 million) | counted up to 10,000, shown as "more than 10,000" | p95 17 ms |
| **Audit sealing** (every minute) asked for unsealed events as a join PostgreSQL could not turn into an anti-join: each batch read the whole chain | 2.9 s per batch at 1.3 million links, growing with the chain; integrity status p95 413 ms | NOT EXISTS (`integrity.unsealed_events`) | 160 ms per batch of 1,000 (any chain length); status p95 171 ms |
| Console: "By department" filters and department columns looked up each department's facility separately | one more query per department on every page | `DepartmentListFilter`, `list_select_related` (7 console lists) | constant query count (CI test) |
| Console lists of the largest tables counted every row twice and read the whole table for the date bar | audit events p95 1.9 s; issued numbers 840 ms; background events 676 ms | `LargeTableAdminMixin`: count up to 10,000, no second count, date filters | 106 ms; 377 ms; 94 ms |

### Final run: all 24 queries and all 30 screens pass

| Screen | p95 | Target |
|---|---|---|
| Who am I (every page load) | 18 ms | 300 ms |
| Bed board (1,500 beds) | 261 ms | 500 ms |
| Staff directory / search | 21 / 22 ms | 500 ms |
| Licence expiry | 83 ms | 300 ms |
| Rota (one department's week) | 116 ms | 500 ms |
| Audit log: newest / one person / one kind / one day / by name | 17 / 18 / 17 / 21 / 30 ms | 500 ms |
| Messages | 80 ms | 500 ms |
| Issued numbers | 171 ms | 500 ms |
| Background jobs: health | 21 ms | 300 ms |
| Retention (with what a purge would delete) | 20 ms | 500 ms |
| Audit integrity status | 171 ms | 300 ms |
| Console: audit events / sign-ins / messages / background events / issued numbers / shifts | 106 / 238 / 71 / 94 / 377 / 197 ms | 500 ms |

The other screens (my sign-ins, hospital settings, facilities, departments, roles, compliance,
security) answered in under 40 ms. The slowest busy queries: the sealing batch 160 ms (budget 250 ms
for a background batch), the integrity waiting count 47 ms, the outbox clean-up 27 ms; every other
query under 10 ms. Sealing the copy's 2 million events from scratch took about 15 minutes, so a
day's backlog after a scheduler outage (about 45,000 events) is sealed in well under a minute.

Every run is also kept on the **Performance** screen of the hospital it was started from.

## Patients and the MPI (HIMS-DATA-003)

The patient part of Artifact A ([review](patients-mpi-review.md)). Run on 2026-11-14 at scale 1 on the same developer PC (PostgreSQL 18.4).

### What the first run found, and the fixes

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

### Final run

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

The Phase 1 results above held: every Phase 1 query and screen passed again in the same run (bed board p95 375 ms, console sign-ins 260 ms, console shifts 269 ms the slowest). The console's issued-numbers list went from 513 ms to 89 ms with its new index.

## Doctor OPD schedules (HIMS-OPD-001)

The schedule part of Artifact A for slice 2B ([review](scheduling.md); HIMS-DATA-004). Run on
2026-11-15 at scale 1 on the same developer PC (5,949,530 rows in all). Added to the synthetic
hospital: 1,002 weekly sessions (three per synthetic doctor) and 1,028 exceptions (two spells away
and one extra session per doctor over a year, a holiday a fortnight).

**What the first run found:** the week screen reads a department's sessions through the department
foreign key's own index, never through the planned (department, weekday) index (the week does not
ask by weekday). That index was dropped before release; the check now expects the foreign key's
index. Everything else passed at once.

| Query | Time | Index |
|---|---|---|
| OPD schedule: one department's sessions | 1.6 ms | department foreign key index |
| OPD schedule: one doctor's sessions | 30.7 ms (the doctor's sessions over a week; under the 100 ms budget) | the no-overlap rule's index `doctor_schedule_no_overlap` |
| OPD schedule: a doctor's time away | 0.4 ms | `schedule_exception_staff_idx` |
| OPD schedule: a facility's holidays | 1.5 ms | read whole (1,028 rows); `schedule_exception_fac_idx` once full reads are ruled out |

| Screen | p95 | Target | Database queries |
|---|---|---|---|
| Doctor schedules (one department's week) | 65 ms | 300 ms | 18 |
| A doctor's free slots on one day | 20 ms | 300 ms | 14 |
| Console: doctor schedules | 135 ms | 500 ms | 8 |

Final run: **44 of 44 queries** use their index in time and **45 of 45 screens** are within target
(the earlier queries and screens held).

## Appointments (HIMS-OPD-002)

The appointments part of Artifact A for slice 2B ([review](scheduling.md#part-2-appointments-hims-opd-002);
HIMS-DATA-004). Run on 2026-11-15 at scale 1 on the same developer PC (6,949,530 rows in all).
Added to the synthetic hospital: **1,000,000 appointments**, five a synthetic doctor a day over about
two years (about 1,500 a day), the last four weeks still to come; past ones completed (one in ten
cancelled, one in twenty did not come), future ones booked (one in ten cancelled). The synthetic
appointments fall on every day while each doctor's weekly session is on one weekday, so nearly every
future booking is "off": the To move list is measured at its worst (a whole department's book).

**What the first run found** (both fixed before release):

1. **Console: appointments** took **2.4 s** (target 500 ms): the list sorted a million rows by day
   with no index for it. Index `appointment_start_idx` (start, newest first) added; the console sorts
   and filters by the start time: **121 ms**.
2. **Appointments to move** took **981 ms**: the query took 31 ms, the rest was reading and listing
   every booked patient of the department. The list now shows the soonest 200 (the next ones appear
   as these are moved), deciding from a few columns and reading the full rows only for those shown:
   450 ms, then **357 ms**.

Earlier, while the index check was written: P0's (facility, day, status) index made PostgreSQL read
one doctor's week through it; it was left out (the OPD queue adds it, HIMS-OPD-003).

| Query | Time | Index |
|---|---|---|
| Appointments: one doctor's week, in their sessions | 1.1 ms | `appointment_staff_day_idx` |
| Appointments: one patient's upcoming ones | 0.1 ms | `appointment_patient_idx` |
| Appointments: one department's booked ones still to come (To move) | 27.1 ms | `appointment_booked_dept_idx` (booked only) |
| Appointments: every appointment, newest first (console list) | 1.1 ms | `appointment_start_idx` |

| Screen | p95 | Target | Database queries |
|---|---|---|---|
| Appointments (one department's day, with the booked patients) | 80 ms | 300 ms | 16 |
| Appointments to move (one department) | 357 ms | 500 ms | 17 |
| A patient's upcoming appointments (chart Overview) | 20 ms | 300 ms | 9 |
| Console: appointments | 121 ms | 500 ms | 8 |

The doctor schedule screens held with a million appointments in their sessions: the week 63 ms, a
doctor's free slots 20 ms. Final run: **48 of 48 queries** use their index in time and **49 of 49
screens** are within target.
