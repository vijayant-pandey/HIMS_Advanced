# Performance checks: indexes and response times (HIMS-DATA-002, HIMS-OPS-017)

**Spec:** 18 (response-time target), 28.6 (indexes checked with production-like volume).
Decision record: [ADR-031](../decisions/ADR-031-performance-targets-and-volume-check.md).
Sizing and the latest results: [volume check](../architecture/data-architecture/volume-check.md).

## In one paragraph

HIMS checks two things as the records grow. The **index check** asks PostgreSQL how it answers
the busiest searches (audit log, sign-ins, messages, rota, background jobs, retention purge...)
and confirms each one uses its index. The **response times** measure how long the main screens
take to answer. The real test is the **volume check**: both run on a throw-away copy filled with
the records of a large hospital (all invented), and the copy is removed afterwards. Every result
is kept on the **Performance** screen and cannot be changed.

## Targets (spec 18)

| What | Target |
|---|---|
| A screen showing one record or a short list | 95 out of 100 answers within **300 ms** |
| A search or long list (audit log, messages, staff, numbers, rota, bed board) | 95 out of 100 within **500 ms** |
| One busy database query | at most **100 ms**, using its index |
| Database queries per screen | must not grow with the number of records |

These are starting targets to confirm with hospitals (spec 18). Availability (99.9%) is measured
once HIMS is hosted.

## Where

- **App:** **Performance** in the menu (needs `platform.performance.view`; the Organization
  administrator has it). Shows the targets, the latest volume-check results, and every check;
  open one to see each query or screen. **Run the index check now** needs
  `platform.performance.manage`; it only reads, takes a few seconds, and is recorded.
- **Admin console:** Performance → **Performance checks**: the same results (read-only) and
  **Run the index check now**.
- **Server (CMD, from `backend` with the virtual environment on):**

| Command | What it does | Time |
|---|---|---|
| `python manage.py volume_check` | The full check at hospital size on a throw-away copy | 30 to 60 minutes (most of it sealing the copy's 2 million audit events) |
| `python manage.py volume_check --scale 0.1` | The same at a tenth of the size | about 5 minutes |
| `python manage.py check_query_plans` | Index check on this hospital's own database (reads only) | seconds |
| `python manage.py measure_response_times` | Response times on this hospital's own database | about a minute |

`volume_check` options: `--keep` keeps the copy (`hims_volume`) to look at it; remove it later with
`python manage.py volume_check --remove-copy`. `--samples 20` sets calls per screen (3 to 25).

## What the volume check does

1. Creates the database `hims_volume` on the same PostgreSQL server (needs the right to create
   databases, as the restore drill does).
2. Migrates it and sets it up like this hospital (same country, time zone and currency).
3. Fills it with synthetic records: 2,000 staff, 1,500 beds, 2 million audit events, 300,000
   sign-ins and messages, 500,000 background events and more (`seed_volume_data`; it refuses any
   database except `hims_volume`).
4. Seals the copy's audit log, as the every-minute job does in a hospital.
5. Runs the index check and the response times on the copy.
6. Records both results in **this** hospital's database (Performance screen, audit log:
   "Performance check run").
7. Removes the copy.

The hospital's own records are never changed: they are only read to copy the country and time zone.

## How response times are measured

A temporary account with administrator and auditor access is created inside a database transaction,
each screen's API (24 app screens and 6 admin-console lists of the largest tables) is called 2 times to warm up and then 20 times, and the transaction is rolled back:
no account, sign-in or audit event is left behind. The calls go through all of Django (sign-in
check, permissions, database) but not the network or the web server, so hosted times will be a
little higher; the load test with many people at once (HIMS-OPS-021) covers that before go-live.
Measuring is refused in hosted environments.

## If a check fails

- **"Reads ... without the expected index":** the query no longer uses its index. Look at what
  changed in the query (a new filter or order) or whether a migration dropped the index. Fix the
  query or add an index (built `CONCURRENTLY` on tables that may already be large), then run the
  volume check again.
- **"Took N ms; the budget is 100 ms":** the index is used but too much is read. Narrow the
  query or the index.
- **"p95 ... is over the target":** open the check, look at the screen's query count, and use the
  index check to find the slow query.
- **"A performance check is already running":** wait a minute; one runs at a time.

## Adding a busy query or screen

Add the query to `backend/apps/performance/queries.py` (built with the app's own code, with the
index that must serve it) and to section 4 of the
[data architecture README](../architecture/data-architecture/README.md); add a main screen to
`ENDPOINTS` in `backend/apps/performance/timings.py`. CI runs the index check and the query-count
check on every pull request.
