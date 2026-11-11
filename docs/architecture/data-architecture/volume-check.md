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
