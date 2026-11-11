# ADR-031: Response-time targets, an index check, and a volume check on a throw-away copy

**Status:** Proposed (2026-11-10) · **Items:** HIMS-DATA-002, HIMS-OPS-017 · **Spec:** 18, 28.6

## Context

Spec 18 sets the starting target "p95 below 300–500 ms for ordinary reads under expected load".
Spec 28.6 asks that indexes be validated "with production-like data volume and query plans". A
developer database has a few hundred rows, where every query is fast whether or not it has an
index. Hosting comes at the end of the build (ADR-027), so there is no real traffic to measure yet.

## Decision

**1. Two targets, per screen.** p95 within **300 ms** for a screen that shows one record or a short
list, and **500 ms** for searches and long lists over the large tables (audit log, messages, staff,
numbers, rota, bed board). Each busy database query has a budget of **100 ms**.

**2. An index check that follows the code.** `apps/performance/queries.py` lists the high-volume
queries, built by the app's own code, each with the index that must serve it. `check_query_plans`
reads PostgreSQL's plan (`EXPLAIN ANALYZE` of SELECTs only, so nothing changes) and fails when an
index is not used or the budget is exceeded. On a small table a full read is rightly quicker, so
the plan is asked again with full reads ruled out and the index must then be chosen: the CI test
runs this way on every pull request, so an index cannot be dropped or forgotten unnoticed.

**3. Response times measured in-process, then rolled back.** `measure_response_times` calls each
main screen's API 20 times through Django's full stack (middleware, sign-in, permissions, database)
as a temporary administrator-and-auditor account created inside a transaction that is rolled back,
so no account, sign-in or audit event is left. It also counts database queries per call; a CI test
fails when a screen's query count grows with the number of records (the "N+1" mistake).

**4. Production-like volume on a throw-away copy.** `volume_check` creates `hims_volume` next to the
hospital's database, migrates it, fills it with synthetic records the size of a 500-bed hospital
(3.6 million rows; sizing in [volume-check.md](../architecture/data-architecture/volume-check.md)),
seals its audit log as the every-minute job would, runs both checks there, records the results in
the hospital's own database (Performance screen, audit log) and removes the copy. The filler
refuses any database except `hims_volume`.

**5. Evidence.** Every result is a row in `performance_checks`, append-only like the audit log,
holding timings, index names and row counts only. The app's Performance screen and the console
show them; the index check can be run from both (it only reads).

**6. Developer PC only for measuring.** Response times and the volume check refuse hosted
environments. There, real traffic is measured by monitoring (HIMS-PLAT-019) and a load test with
many people at once runs against the staging environment before go-live (HIMS-OPS-021).

## Consequences

- The first volume checks found six real problems, fixed in the same change: no index for the
  retention purge's "ended before" search (`user_session_ended_idx`); the failed-events count on the
  background-jobs page reading the whole outbox (`outbox_attention_idx`); purge batches forcing an
  id order that stopped the date index being used; the audit log's total count growing with the
  log (now counted up to 10,000, shown as "more than 10,000"); the every-minute **audit sealing**
  asking for unsealed events in a form PostgreSQL could not turn into an anti-join, so every batch
  read the whole chain (2.9 s at 1.3 million links, now 0.09 s, written as NOT EXISTS); and the
  console's "By department" filters and lists looking up each department's facility one query at a
  time; and the console lists of the largest tables counting every row twice and reading the whole
  table for their date bar (audit events 1.9 s at 2 million): they now count up to 10,000 ("More than
  10,000") and filter dates with Today / Past 7 days / This month (`LargeTableAdminMixin`).
- New indexes on tables that may already be large in a hospital are built `CONCURRENTLY`, so sign-ins
  and background jobs are not blocked while they build.
- In-process timings leave out the network and the web server's worker pool; they are a baseline and
  a regression guard, not the final word. The load test (HIMS-OPS-021) covers the rest.
- Adding a busy query to the app means adding it to `queries.py` and to section 4 of the data
  architecture README; a test keeps the two in step.
