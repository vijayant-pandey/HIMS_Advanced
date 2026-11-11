# Requirement records: platform, operations, data, tests and documents

Spec sections 6, 14, 16, 18, 19, 25, 28, 29, 31–35. Format: [README](README.md). Endpoints:
[background jobs](../architecture/api-and-integrations/endpoints/outbox.md),
[backups](../architecture/api-and-integrations/endpoints/recovery.md),
[performance](../architecture/api-and-integrations/endpoints/performance.md),
[API endpoints list](../architecture/api-and-integrations/endpoints/contracts.md).

Most platform requirements have no screen of their own: they are rules every endpoint follows, so
their "actors" are every caller and their evidence is the shared tests in `backend/common/tests/`.

## Platform

### HIMS-PLAT-001

| Field | Record |
|---|---|
| ID and title | HIMS-PLAT-001 Repository layout (spec 8); Django, DRF and Celery project; settings per environment |
| Business/clinical reason | One modular monolith that every developer and CI run the same way (spec 6.1, 8). Owner: PO |
| Actors | Developers; CI |
| Preconditions | None |
| Main success path | `backend/` (domain apps), `frontend/`, `docs/`; settings for local, test and each hosted environment |
| Alternate/failure paths | An unknown environment name fails at start |
| Data effects | None |
| Security classification | Not applicable |
| Audit requirement | None |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | PostgreSQL; Redis optional locally |
| Acceptance criteria | `manage.py check` passes in every environment's settings |
| Test evidence | `common/tests/test_environment.py`; CI job "backend" |
| Release risk | None at runtime |

### HIMS-PLAT-002

| Field | Record |
|---|---|
| ID and title | HIMS-PLAT-002 Start-up guard: a developer PC cannot reach a hosted database; the database secret must match the environment |
| Business/clinical reason | A test run must never touch a real hospital's data (spec 31). Owner: PO |
| Actors | Every process start |
| Preconditions | Environment settings |
| Main success path | Start-up checks the environment name against the database host and secret |
| Alternate/failure paths | Mismatch → the process refuses to start with the reason (no URL printed) |
| Data effects | None |
| Security classification | Credentials (restricted) |
| Audit requirement | None (refuses before running) |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | None |
| Acceptance criteria | Local settings with a hosted database URL never start |
| Test evidence | `common/tests/test_environment.py` |
| Release risk | Data safety |

### HIMS-PLAT-003

| Field | Record |
|---|---|
| ID and title | HIMS-PLAT-003 Problem Details errors (RFC 9457) with per-field validation errors |
| Business/clinical reason | Every error has one shape, a stable code and a request ID, and never shows internals (spec 29.1, 29.2). Owner: PO |
| Actors | Every endpoint |
| Preconditions | None |
| Main success path | Errors return `type`, `title`, `status`, `detail`, `code`, `request_id` and, for validation, `errors` per field |
| Alternate/failure paths | Unexpected failures → 500 `INTERNAL_ERROR` with the request ID only; the detail is logged and traced, filtered |
| Data effects | None |
| Security classification | Not applicable |
| Audit requirement | 403s record `access.denied` |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | None |
| Acceptance criteria | No stack trace or SQL text in any response |
| Test evidence | `common/tests/test_api_conventions.py` |
| Release risk | Low |

### HIMS-PLAT-004

| Field | Record |
|---|---|
| ID and title | HIMS-PLAT-004 Request (correlation) ID through logs, audit, outbox and background jobs |
| Business/clinical reason | One ID follows a request everywhere, so support can trace a problem the user reports (spec 29.1). Owner: PO |
| Actors | Every request and job |
| Preconditions | None |
| Main success path | A safe incoming `X-Request-ID` is kept, otherwise one is made; it is returned, logged, stored on audit and outbox rows and passed to jobs |
| Alternate/failure paths | An unsafe incoming value is replaced |
| Data effects | The request ID column of `audit_events` and `outbox_events` |
| Security classification | Not applicable |
| Audit requirement | Every event carries it |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | None |
| Acceptance criteria | The reference on the "no access" page finds the audit event |
| Test evidence | `common/tests/test_api_conventions.py`, `common/tests/test_outbox.py` |
| Release risk | Low |

### HIMS-PLAT-005

| Field | Record |
|---|---|
| ID and title | HIMS-PLAT-005 JSON logs with deployment, environment and release |
| Business/clinical reason | Logs from many hospitals must be told apart and searched. Owner: PO |
| Actors | Every log line |
| Preconditions | None |
| Main success path | One JSON object per line with the standard fields and the request ID |
| Alternate/failure paths | Secrets are filtered (HIMS-SEC-019) |
| Data effects | None |
| Security classification | Not applicable |
| Audit requirement | None |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | Log collector at hosting |
| Acceptance criteria | Every line parses as JSON with the fields |
| Test evidence | `common/tests/test_log_safety.py` |
| Release risk | Low |

### HIMS-PLAT-006

| Field | Record |
|---|---|
| ID and title | HIMS-PLAT-006 `Idempotency-Key`: replay, conflict, concurrent duplicates |
| Business/clinical reason | A double click or a retried request must not create two records (spec 29.3). Owner: PO |
| Actors | Clients of the 41 endpoints that take it |
| Preconditions | None |
| Main success path | The first request stores its answer under the key; the same key and body replays it |
| Alternate/failure paths | Same key, different body → 409 `IDEMPOTENCY_KEY_REUSED`; invalid key → 400; error answers are not stored |
| Data effects | `idempotency_records` (kept 48 hours, then purged hourly) |
| Security classification | Not applicable |
| Audit requirement | Only the first request's change is audited |
| Idempotency/concurrency | Concurrent duplicates wait on a unique index and replay |
| Integration dependencies | None |
| Acceptance criteria | Two parallel requests with one key create one record |
| Test evidence | `common/tests/test_idempotency.py` |
| Release risk | Low |

### HIMS-PLAT-007

| Field | Record |
|---|---|
| ID and title | HIMS-PLAT-007 Transactional outbox, SKIP LOCKED dispatcher, consumer de-duplication (ADR-012) |
| Business/clinical reason | Background work (messages, follow-ups) happens exactly when the change commits, never for a rolled-back change (spec 14.2, 29.7). Owner: PO |
| Actors | Services publish; the dispatcher (Celery) delivers; `platform.jobs.view`, `platform.jobs.manage` |
| Preconditions | None |
| Main success path | The event is saved in the same transaction; the dispatcher sends it; consumers record what they processed |
| Alternate/failure paths | Failures retry with back-off up to 12 times, then dead; publishing outside a transaction is refused |
| Data effects | `outbox_events`, `outbox_processed_events` |
| Security classification | Internal (payloads minimal, no secrets) |
| Audit requirement | `outbox.event_sent_again`, `outbox.event_dismissed` |
| Idempotency/concurrency | Consumers de-duplicate by event ID; SKIP LOCKED lets several dispatchers run |
| Integration dependencies | Redis broker at hosting; inline locally |
| Acceptance criteria | No event without its change, no change without its event |
| Test evidence | `common/tests/test_outbox.py` |
| Release risk | Operational |

### HIMS-PLAT-008

| Field | Record |
|---|---|
| ID and title | HIMS-PLAT-008 Version checks (`version`) on editable records |
| Business/clinical reason | Two people editing at once must not silently overwrite each other (spec 10, 29.3). Owner: PO |
| Actors | Every change endpoint with a `version` |
| Preconditions | None |
| Main success path | The client sends the version it read; the server locks the row, compares, saves and adds one |
| Alternate/failure paths | Different version → 409 `STALE_RESOURCE`, nothing saved |
| Data effects | The version column of each editable table (for example `facilities`, `departments`, `roles`) |
| Security classification | Not applicable |
| Audit requirement | Only saved changes are audited |
| Idempotency/concurrency | Row lock plus version |
| Integration dependencies | None |
| Acceptance criteria | Every contract with a `version` field documents the 409 |
| Test evidence | `common/tests/test_api_conventions.py`; per-area tests |
| Release risk | Low |

### HIMS-PLAT-009

| Field | Record |
|---|---|
| ID and title | HIMS-PLAT-009 Health endpoints (`/health/live/`, `/health/ready/`) |
| Business/clinical reason | Hosting restarts or holds traffic from a broken process. Owner: PO |
| Actors | Load balancer, container platform (no sign-in; not under `/api/v1/`) |
| Preconditions | None |
| Main success path | Live answers if the process runs; ready also checks the database |
| Alternate/failure paths | Database down → ready answers 503 |
| Data effects | None |
| Security classification | Public (no data) |
| Audit requirement | None |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | PostgreSQL |
| Acceptance criteria | Ready fails within seconds of a database outage |
| Test evidence | `common/tests/test_api_conventions.py` |
| Release risk | Low |

### HIMS-PLAT-010

| Field | Record |
|---|---|
| ID and title | HIMS-PLAT-010 OpenAPI contract generated and checked; frontend types generated from it |
| Business/clinical reason | The screens and the API must agree, and changes to the API must be seen (spec 29.1, 29.9). Owner: PO |
| Actors | CI; developers |
| Preconditions | None |
| Main success path | `docs/api/openapi.yaml` is generated from the code on an empty database; `frontend/src/api/schema.d.ts` from it |
| Alternate/failure paths | Any difference fails CI ("OpenAPI contract is up to date") |
| Data effects | None |
| Security classification | Not applicable |
| Audit requirement | None |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | None |
| Acceptance criteria | A changed field without a regenerated contract never merges |
| Test evidence | CI jobs "backend" and "frontend"; `docs/workflows/before-you-push.md` |
| Release risk | Low |

### HIMS-PLAT-011

| Field | Record |
|---|---|
| ID and title | HIMS-PLAT-011 One container image for web, worker and scheduler; runs as a non-root user |
| Business/clinical reason | What was tested is what runs (spec 33). Owner: PO |
| Actors | CI builds; hosting runs |
| Preconditions | None |
| Main success path | `backend/Dockerfile` builds one image; the role is chosen by the command |
| Alternate/failure paths | Build failure fails CI |
| Data effects | None |
| Security classification | Not applicable |
| Audit requirement | None |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | Container registry at hosting |
| Acceptance criteria | The image runs as a non-root user |
| Test evidence | CI job "image" |
| Release risk | Low |

### HIMS-PLAT-012

| Field | Record |
|---|---|
| ID and title | HIMS-PLAT-012 Hash-locked Python lockfile (`--require-hashes` in CI and the image) |
| Business/clinical reason | A changed package on the internet cannot slip into a build (supply chain). Owner: PO |
| Actors | CI, image build |
| Preconditions | None |
| Main success path | Every package is installed only if its hash matches |
| Alternate/failure paths | A mismatch stops the install |
| Data effects | None |
| Security classification | Not applicable |
| Audit requirement | None |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | Package index |
| Acceptance criteria | Lockfile hashes cover every platform |
| Test evidence | `common/tests/test_dependencies.py` |
| Release risk | Low |

### HIMS-PLAT-013

| Field | Record |
|---|---|
| ID and title | HIMS-PLAT-013 GitHub Actions pinned to commit hashes; least-privilege tokens; Dependabot |
| Business/clinical reason | A changed third-party action cannot run in our CI (supply chain). Owner: PO |
| Actors | CI |
| Preconditions | None |
| Main success path | Every action pinned by hash with its version noted; each job asks only for the permissions it needs |
| Alternate/failure paths | An unpinned action or a broad token fails a test |
| Data effects | None |
| Security classification | Not applicable |
| Audit requirement | None |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | GitHub |
| Acceptance criteria | The test finds no tag-pinned action |
| Test evidence | `common/tests/test_ci_workflows.py` |
| Release risk | Low |

### HIMS-PLAT-014

| Field | Record |
|---|---|
| ID and title | HIMS-PLAT-014 Outbox and idempotency clean-up jobs, health and runbook; Background jobs page |
| Business/clinical reason | Tables must not grow forever, and failed background work must be seen and decided (spec 14.3). Owner: PO |
| Actors | Daily and hourly jobs; `platform.jobs.view`, `platform.jobs.manage` |
| Preconditions | HIMS-PLAT-007 |
| Main success path | Published events older than 30 days and expired idempotency records are deleted in batches; the page shows health, failed events, Send again and Dismiss with a reason |
| Alternate/failure paths | Dead events stay until decided |
| Data effects | `outbox_events`, `idempotency_records` |
| Security classification | Internal |
| Audit requirement | `outbox.cleaned_up`, `outbox.event_sent_again`, `outbox.event_dismissed` |
| Idempotency/concurrency | Clean-up repeatable; decisions under row locks |
| Integration dependencies | None |
| Acceptance criteria | The health check stays fast at 500,000 events (21 ms) |
| Test evidence | `common/tests/test_outbox_maintenance.py`; manual test Part 18d |
| Release risk | Low ([runbook](../runbooks/outbox-and-background-jobs.md)) |

### HIMS-PLAT-015

| Field | Record |
|---|---|
| ID and title | HIMS-PLAT-015 Screens loaded per page (code splitting); first download budget 500 kB |
| Business/clinical reason | The app opens quickly on hospital networks (spec 18). Owner: PO |
| Actors | Browsers |
| Preconditions | None |
| Main success path | Each page is a separate download; the first stays under 500 kB |
| Alternate/failure paths | Over budget fails CI; after an update the page reloads once |
| Data effects | None |
| Security classification | Not applicable |
| Audit requirement | None |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | None |
| Acceptance criteria | First download within budget (480 kB) |
| Test evidence | CI "Bundle size" step |
| Release risk | Low |

### HIMS-PLAT-016

| Field | Record |
|---|---|
| ID and title | HIMS-PLAT-016 OpenTelemetry tracing for API, database, jobs and outbound calls; off by default; no personal data (ADR-021) |
| Business/clinical reason | Slow requests can be followed through every step (spec 18). Owner: PO |
| Actors | Every request and job when switched on |
| Preconditions | `HIMS_TRACING_EXPORTER` |
| Main success path | Spans with route templates (not real paths) and the request ID |
| Alternate/failure paths | Collector down → spans dropped, requests unaffected |
| Data effects | None |
| Security classification | Internal; error text filtered (HIMS-SEC-020) |
| Audit requirement | None |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | Trace collector (hosting, HIMS-PLAT-019) |
| Acceptance criteria | No identifiers or query strings in span names |
| Test evidence | `common/tests/test_tracing.py` |
| Release risk | Low |

### HIMS-PLAT-017

| Field | Record |
|---|---|
| ID and title | HIMS-PLAT-017 Operations console (Django admin): role-gated, audited, no deletion (ADR-016) |
| Business/clinical reason | Support staff need a full console that follows the same rules as the app. Owner: PO |
| Actors | `platform.admin_console`; auditors (`audit.view`) see only the audit log |
| Preconditions | Two-factor for privileged users; allowed address (HIMS-SEC-015) |
| Main success path | Every change goes through the same services as the API and is audited |
| Alternate/failure paths | No delete buttons; no superuser bypass |
| Data effects | All tables, through services |
| Security classification | Restricted |
| Audit requirement | Each service's events |
| Idempotency/concurrency | As each service |
| Integration dependencies | None |
| Acceptance criteria | Nothing can be deleted from the console |
| Test evidence | `common/admin/tests/test_admin_console.py`; browser test `05-admin-console.spec.ts`; manual test Part 18 |
| Release risk | Operational |

### HIMS-PLAT-018

| Field | Record |
|---|---|
| ID and title | HIMS-PLAT-018 Console covers every model (test-enforced), with the app's actions |
| Business/clinical reason | "Each and everything managed in admin" (PO). Owner: PO |
| Actors | Console users |
| Preconditions | HIMS-PLAT-017 |
| Main success path | Every model is registered; the app's actions (send again, dismiss, exports, status pages, this list of API endpoints) exist in the console too |
| Alternate/failure paths | A new model without a console page fails the test |
| Data effects | None |
| Security classification | Restricted |
| Audit requirement | As each service |
| Idempotency/concurrency | As each service |
| Integration dependencies | None |
| Acceptance criteria | The coverage test passes |
| Test evidence | `common/admin/tests/test_admin_coverage.py`, `common/admin/tests/test_console_additions.py` |
| Release risk | Low |

## Screens

### HIMS-UI-001

| Field | Record |
|---|---|
| ID and title | HIMS-UI-001 Theme selector across the launcher, the app and the console |
| Business/clinical reason | Readable colours for long shifts and different screens. Owner: PO |
| Actors | Anyone |
| Preconditions | None |
| Main success path | Choose one of 10 themes; it applies everywhere and is remembered |
| Alternate/failure paths | Unknown theme → default |
| Data effects | Browser storage and a cookie |
| Security classification | Not applicable |
| Audit requirement | None |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | None |
| Acceptance criteria | Text contrast meets WCAG AA in every theme (axe in browser tests) |
| Test evidence | `common/tests/test_theming.py`; frontend `themes.test.ts`; browser tests with axe |
| Release risk | None |

### HIMS-UI-002

| Field | Record |
|---|---|
| ID and title | HIMS-UI-002 "No access yet" welcome page and menus that follow permissions |
| Business/clinical reason | New staff without a role see a friendly page with a reference, not an error. Owner: PO |
| Actors | Anyone signed in without a role |
| Preconditions | Signed in |
| Main success path | The welcome page shows the reference; the visit is recorded so an administrator can find it |
| Alternate/failure paths | Menus never show items the person cannot open (the API still enforces) |
| Data effects | `audit_events` |
| Security classification | Not applicable |
| Audit requirement | `access.none_assigned` |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | None |
| Acceptance criteria | The reference finds the event in the audit log |
| Test evidence | `apps/identity/tests/test_no_access.py`; manual test Part 9 |
| Release risk | None |

## Operations

### HIMS-OPS-001

| Field | Record |
|---|---|
| ID and title | HIMS-OPS-001 Pull request checks: lint, types, migrations, tests on PostgreSQL, contract drift, audits, image, secret scan |
| Business/clinical reason | Nothing broken reaches `development` (spec 33). Owner: PO |
| Actors | GitHub Actions on every PR |
| Preconditions | None |
| Main success path | `.github/workflows/pull-request-ci.yml` runs every check; `browser-tests.yml` runs the browser tests |
| Alternate/failure paths | Any failure blocks the merge |
| Data effects | None |
| Security classification | Not applicable |
| Audit requirement | GitHub keeps the runs |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | GitHub |
| Acceptance criteria | Every lesson from a failed run is in `docs/workflows/before-you-push.md` |
| Test evidence | `common/tests/test_ci_workflows.py` |
| Release risk | None |

### HIMS-OPS-002

| Field | Record |
|---|---|
| ID and title | HIMS-OPS-002 GitHub repository, environment branches (`development`, `qa`, `staging`, `production`), required checks |
| Business/clinical reason | Changes are promoted in order (spec 32). Owner: PO |
| Actors | The PO (merges); GitHub |
| Preconditions | None |
| Main success path | Feature branch → PR into `development` → squash merge |
| Alternate/failure paths | Direct pushes to environment branches blocked |
| Data effects | None |
| Security classification | Not applicable |
| Audit requirement | GitHub history |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | GitHub |
| Acceptance criteria | Required checks enforced on `development` |
| Test evidence | PR history in `docs/status/spec-status.md` |
| Release risk | None |

### HIMS-OPS-007

| Field | Record |
|---|---|
| ID and title | HIMS-OPS-007 Separate database users: app, migration, read-only, break-glass |
| Business/clinical reason | The running app must not be able to change the schema or the audit log (spec 13.2, 17.2). Owner: PO |
| Actors | Database owner (setup command); the app connects as its own user |
| Preconditions | PostgreSQL owner access |
| Main success path | `setup_database_users` creates the users and rights; the Compliance page shows the checks |
| Alternate/failure paths | A failed check shows on the page and the console |
| Data effects | Database roles and grants |
| Security classification | Credentials (restricted) |
| Audit requirement | `database.users_set_up` |
| Idempotency/concurrency | The command is repeatable |
| Integration dependencies | PostgreSQL |
| Acceptance criteria | The app user cannot UPDATE, DELETE or TRUNCATE `audit_events` |
| Test evidence | `common/tests/test_database_roles.py`; manual test Part 18c |
| Release risk | Operational ([how-to](../workflows/database-users.md)) |

### HIMS-OPS-009

| Field | Record |
|---|---|
| ID and title | HIMS-OPS-009 Backups and restore drills with checks of relationships and the audit chain |
| Business/clinical reason | A backup is worth only what a tested restore proves (spec 27). Owner: PO |
| Actors | `recovery.view`, `recovery.manage` |
| Preconditions | PostgreSQL tools on the server |
| Main success path | Back up the database and documents; restore into a separate database; compare counts, relationships and the audit chain |
| Alternate/failure paths | Tool failure → `RECOVERY_FAILED`; a failed check marks the drill failed |
| Data effects | `recovery_backups`, `recovery_restore_drills` |
| Security classification | Restricted (backups hold everything) |
| Audit requirement | `recovery.backup.created`, `recovery.restore_drill.completed` |
| Idempotency/concurrency | One at a time |
| Integration dependencies | pg_dump, pg_restore |
| Acceptance criteria | A drill proves the copy matches |
| Test evidence | `apps/recovery/tests/test_restore_drill.py`; manual test Part 18b |
| Release risk | Data loss if backups fail unnoticed (Backups page shows the last one) |

### HIMS-OPS-010

| Field | Record |
|---|---|
| ID and title | HIMS-OPS-010 Console and API docs files served by the app; Swagger UI bundled, no outside sites |
| Business/clinical reason | Hosted environments must work without a CDN and without loading outside scripts. Owner: PO |
| Actors | Browsers |
| Preconditions | Image built |
| Main success path | Files collected at build and served compressed by WhiteNoise |
| Alternate/failure paths | A missing file fails the static files test |
| Data effects | None |
| Security classification | Public |
| Audit requirement | None |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | None |
| Acceptance criteria | API docs open with no request to another site |
| Test evidence | `common/tests/test_static_files.py`; manual test Part 18e |
| Release risk | Low |

### HIMS-OPS-012

| Field | Record |
|---|---|
| ID and title | HIMS-OPS-012 Runbook: updating every hospital database after a merge |
| Business/clinical reason | Each hospital has its own database; none may be left behind. Owner: PO |
| Actors | The PO or operator |
| Preconditions | Merged migrations |
| Main success path | Follow [database migrations](../workflows/database-migrations.md) for each hospital |
| Alternate/failure paths | A failed migration is rolled back by PostgreSQL; the runbook says what to do |
| Data effects | Schema changes |
| Security classification | Not applicable |
| Audit requirement | None |
| Idempotency/concurrency | `migrate` is repeatable |
| Integration dependencies | None |
| Acceptance criteria | Both local hospitals migrate after every PR |
| Test evidence | Manual: each PR's migrate step |
| Release risk | Operational |

### HIMS-OPS-016

| Field | Record |
|---|---|
| ID and title | HIMS-OPS-016 Phase 1 manual test guide for the product owner |
| Business/clinical reason | The PO checks every feature in the browser before it counts as released (spec 35). Owner: PO |
| Actors | The PO |
| Preconditions | Both hospitals running |
| Main success path | [flow-part1.md](../testing/flow-part1.md) lists each step and its expected result |
| Alternate/failure paths | A step that does not match is reported |
| Data effects | None |
| Security classification | Not applicable |
| Audit requirement | None |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | None |
| Acceptance criteria | Every built feature has a part |
| Test evidence | The guide itself |
| Release risk | None |

### HIMS-OPS-017

| Field | Record |
|---|---|
| ID and title | HIMS-OPS-017 Response-time targets measured locally before hosting (spec 18) |
| Business/clinical reason | Screens 300 ms, searches 500 ms (95 of 100 requests) at hospital size. Owner: PO |
| Actors | `platform.performance.view`, `platform.performance.manage`; developers run `volume_check` |
| Preconditions | Developer PC |
| Main success path | 30 screens measured on a 3.6-million-row copy; results kept |
| Alternate/failure paths | Hosted environments refuse to measure here (load test HIMS-OPS-021) |
| Data effects | `performance_checks` (append-only) |
| Security classification | Internal |
| Audit requirement | `performance.check_run` |
| Idempotency/concurrency | One check at a time (advisory lock) |
| Integration dependencies | None |
| Acceptance criteria | All 30 screens within target in the final run |
| Test evidence | `apps/performance/tests/test_performance.py`; manual test Part 18q |
| Release risk | None |

## Data, tests and documents

### HIMS-DATA-001

| Field | Record |
|---|---|
| ID and title | HIMS-DATA-001 Data dictionary and ERDs generated from the models, checked in CI |
| Business/clinical reason | Artifact A (spec 28): every table and column documented and never out of date. Owner: PO |
| Actors | Developers; CI |
| Preconditions | None |
| Main success path | `python manage.py data_dictionary` writes the dictionary and diagrams |
| Alternate/failure paths | Out of date → CI fails |
| Data effects | None |
| Security classification | Not applicable |
| Audit requirement | None |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | None |
| Acceptance criteria | Every column has a meaning and a sensitivity class |
| Test evidence | `common/tests/test_data_dictionary.py` |
| Release risk | None |

### HIMS-DATA-002

| Field | Record |
|---|---|
| ID and title | HIMS-DATA-002 Indexes checked with production-size synthetic data and query plans (spec 28.6) |
| Business/clinical reason | Queries that are fast on test data can be slow at hospital size. Owner: PO |
| Actors | `platform.performance.manage` (index check in the app); developers (`volume_check`) |
| Preconditions | Developer PC for the volume copy |
| Main success path | The 24 busiest queries' plans are checked on a throw-away copy; results kept |
| Alternate/failure paths | The seed command refuses any database but the throw-away one |
| Data effects | `performance_checks` |
| Security classification | Internal (synthetic records only) |
| Audit requirement | `performance.check_run` |
| Idempotency/concurrency | One check at a time |
| Integration dependencies | None |
| Acceptance criteria | 24 of 24 queries use their index in time |
| Test evidence | `apps/performance/tests/test_performance.py`; [volume check](../architecture/data-architecture/volume-check.md) |
| Release risk | None |

### HIMS-QA-001

| Field | Record |
|---|---|
| ID and title | HIMS-QA-001 Browser tests for Phase 1 flows with accessibility checks |
| Business/clinical reason | The screens are tested as people use them, including keyboard and contrast (spec 19.2). Owner: PO |
| Actors | CI ("browser-tests" workflow) |
| Preconditions | A throw-away database and server |
| Main success path | Playwright runs the India and console tests with axe |
| Alternate/failure paths | A failure keeps screenshots and traces as artifacts |
| Data effects | Throw-away database only |
| Security classification | Synthetic data only |
| Audit requirement | None |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | None |
| Acceptance criteria | No serious accessibility finding |
| Test evidence | `frontend/e2e/tests/`; [browser tests](../testing/browser-tests.md) |
| Release risk | None |

### HIMS-QA-003

| Field | Record |
|---|---|
| ID and title | HIMS-QA-003 Browser tests for the US hospital and the admin console |
| Business/clinical reason | The second country and the console are tested like the first (spec 19.2). Owner: PO |
| Actors | CI |
| Preconditions | US throw-away deployment |
| Main success path | `npm run e2e:us` runs a separate US hospital; console tests run with the India ones |
| Alternate/failure paths | As HIMS-QA-001 |
| Data effects | Throw-away databases |
| Security classification | Synthetic data only |
| Audit requirement | None |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | None |
| Acceptance criteria | 12 US and 43 India and console tests pass |
| Test evidence | `frontend/e2e/us/01-us-hospital.spec.ts`, `frontend/e2e/tests/05-admin-console.spec.ts` |
| Release risk | None |

### HIMS-DOC-001

| Field | Record |
|---|---|
| ID and title | HIMS-DOC-001 Requirement records and per-endpoint contract documents for everything built (spec 25.3, 25.4, 29) |
| Business/clinical reason | Each requirement traces to its code, endpoints, tests and PRs; each endpoint has a written contract that cannot drift from the code (spec 25.3, 29.5, 29.9). Owner: PO |
| Actors | Developers and CI (`api_contracts`); `access.roles.view` sees the API endpoints list in the app and the console |
| Preconditions | Backlog, PR history, `docs/api/openapi.yaml` |
| Main success path | Contracts are generated from the code into `docs/architecture/api-and-integrations/endpoints/`; records written here; the matrix generated |
| Alternate/failure paths | A new view without a requirement, a Done ticket without a record, an empty record field or out-of-date files fail CI |
| Data effects | None (reads code and files) |
| Security classification | Internal: names permissions, not secrets |
| Audit requirement | None (read only) |
| Idempotency/concurrency | Read only |
| Integration dependencies | None |
| Acceptance criteria | Every endpoint (240 when built) documented in the 29.5 template; every Done requirement has a complete record; the app and console list match the code |
| Test evidence | `common/contracts/tests/test_contracts.py`; frontend `AccessPage.test.tsx`; manual test Part 18r |
| Release risk | None (documents and a read-only list) |
