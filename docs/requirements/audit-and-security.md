# Requirement records: audit log and security

Spec sections 4.25, 13. Format: [README](README.md). Endpoints:
[audit](../architecture/api-and-integrations/endpoints/audit.md),
[compliance and security](../architecture/api-and-integrations/endpoints/compliance.md).

### HIMS-AUD-001

| Field | Record |
|---|---|
| ID and title | HIMS-AUD-001 Append-only audit events (database trigger); audit search, itself audited (ADR-013) |
| Business/clinical reason | Every change and every refusal must be provable later (spec 13.4; HIPAA, DPDP). Owner: compliance |
| Actors | Every service writes events; `audit.view` (auditor) searches |
| Preconditions | None |
| Main success path | Each change writes an event with who, what, when, where (address), request ID and before/after; auditors search by person, area, record, day |
| Alternate/failure paths | Any UPDATE, DELETE or TRUNCATE on the table is refused by the database; the app's database user lacks the rights too (HIMS-OPS-007) |
| Data effects | `audit_events` |
| Security classification | Audit evidence (restricted) |
| Audit requirement | Searches record `audit.events.searched` |
| Idempotency/concurrency | Insert only |
| Integration dependencies | None |
| Acceptance criteria | No code path can change or delete an event (trigger test); the count stays fast at 2 million events (counted to 10,000) |
| Test evidence | `apps/audit/tests/test_audit.py`, `common/tests/test_database_roles.py` |
| Release risk | Compliance if lost. Rollback: none (append-only by design) |

### HIMS-AUD-002

| Field | Record |
|---|---|
| ID and title | HIMS-AUD-002 Access-denied events recorded even when the request's transaction rolls back |
| Business/clinical reason | Refused attempts are the most important events to keep. Owner: compliance |
| Actors | Every endpoint (the error handler) |
| Preconditions | None |
| Main success path | A 403 writes `access.denied` with the request ID, which the user sees as a reference |
| Alternate/failure paths | If writing the event fails, it is logged and the 403 still goes out |
| Data effects | `audit_events` |
| Security classification | Audit evidence (restricted) |
| Audit requirement | `access.denied` |
| Idempotency/concurrency | Written outside the rolled-back transaction |
| Integration dependencies | None |
| Acceptance criteria | A refused write leaves its refusal on record |
| Test evidence | `apps/audit/tests/test_audit.py`, `apps/access_control/tests/test_authorization.py` |
| Release risk | Compliance |

### HIMS-AUD-003

| Field | Record |
|---|---|
| ID and title | HIMS-AUD-003 Audit log screen for auditors, with CSV download |
| Business/clinical reason | Auditors work in the app, not the database. Owner: compliance |
| Actors | `audit.view` |
| Preconditions | HIMS-AUD-001 |
| Main success path | Search with filters; open details; download up to 5,000 events as CSV after "confirm it's you" |
| Alternate/failure paths | Over 10,000 matches → "more than 10,000", narrow the filters |
| Data effects | Reads `audit_events` |
| Security classification | Audit evidence (restricted) |
| Audit requirement | `audit.events.searched`, `audit.events.exported` |
| Idempotency/concurrency | Read only |
| Integration dependencies | None |
| Acceptance criteria | Every search and download is itself on record; the Area list matches the server's (test) |
| Test evidence | `apps/audit/tests/test_audit_screen.py`, `apps/audit/tests/test_audit_areas.py`; browser test `04-audit-and-safety.spec.ts`; manual test Part 17 |
| Release risk | Low |

### HIMS-SEC-010

| Field | Record |
|---|---|
| ID and title | HIMS-SEC-010 Audit tamper evidence: keyed hash chain, sealed every minute, daily and on-demand checks |
| Business/clinical reason | Even a database owner must not be able to change history unnoticed (spec 13.4). Owner: compliance |
| Actors | Every-minute job (seal), daily job (check), `audit.view` (check on demand) |
| Preconditions | Chain key configured |
| Main success path | New events are linked into the chain; checks recompute it and report breaks; alerts go to the compliance team |
| Alternate/failure paths | A changed, deleted or inserted event breaks the chain and is reported with its link number |
| Data effects | `audit_chain_entries`, `audit_integrity_checks` |
| Security classification | Audit evidence (restricted) |
| Audit requirement | `audit.integrity.checked`, `audit.integrity.alert_sent` |
| Idempotency/concurrency | One sealer at a time (lock); unsealed events found with NOT EXISTS (0.16 s per 1,000 at any chain length) |
| Integration dependencies | Email alerts |
| Acceptance criteria | Any tampering is found by the next check |
| Test evidence | `apps/audit/tests/test_integrity.py`; manual test Part 17 |
| Release risk | Compliance. Copy of the chain head off-site: HIMS-SEC-016 (hosting) |

### HIMS-SEC-012

| Field | Record |
|---|---|
| ID and title | HIMS-SEC-012 Security headers and content security policy for screens, console and API; reports of anything blocked |
| Business/clinical reason | Browsers refuse injected scripts and framing (spec 13.3). Owner: PO |
| Actors | Every response; browsers send reports (no sign-in); `compliance.view`, `compliance.manage` review them |
| Preconditions | None |
| Main success path | Headers on every response; blocked content reported, stored and reviewed |
| Alternate/failure paths | Oversized or flooding reports → refused (size limit, 30 a minute) |
| Data effects | `browser_security_reports` |
| Security classification | Security event (internal) |
| Audit requirement | `compliance.browser_report.reviewed` |
| Idempotency/concurrency | Repeated reports are counted, not duplicated |
| Integration dependencies | Hosting must send the screens' headers (HIMS-SEC-018) |
| Acceptance criteria | Every API and console response carries the headers (test) |
| Test evidence | `apps/compliance/tests/test_browser_reports.py`, `common/tests/test_client_ip_and_headers.py` |
| Release risk | Low; report-only mode exists for rollout |

### HIMS-SEC-013

| Field | Record |
|---|---|
| ID and title | HIMS-SEC-013 Virus scanning of every upload |
| Business/clinical reason | Uploaded files must not carry malware into the hospital (spec 13.3). Owner: PO |
| Actors | Every upload; `compliance.manage` scans stored documents on demand |
| Preconditions | ClamAV reachable (or the stand-in scanner on a developer PC) |
| Main success path | Each file is scanned before it is stored; the result is kept with the file |
| Alternate/failure paths | Virus → refused, audited, compliance team told; scanner unreachable → upload refused (`SCANNER_UNAVAILABLE`), never stored unchecked |
| Data effects | `staff_documents` scan fields, `organizations.logo` |
| Security classification | Security event (internal) |
| Audit requirement | `upload.blocked`, `staff.document.virus_found`, `staff.documents.scanned` |
| Idempotency/concurrency | Scanning stored files is repeatable |
| Integration dependencies | ClamAV, 30 s timeout |
| Acceptance criteria | The test virus signature is always refused |
| Test evidence | `common/tests/test_virus_scan.py`; manual test Part 18n |
| Release risk | Availability if the scanner is down (uploads wait). Rollback: none needed |

### HIMS-SEC-014

| Field | Record |
|---|---|
| ID and title | HIMS-SEC-014 Trust `X-Forwarded-For` only from our own proxies |
| Business/clinical reason | Audit addresses and rate limits must use the real client address (spec 13.1). Owner: PO |
| Actors | Every request |
| Preconditions | `HIMS_TRUSTED_PROXIES` at hosting |
| Main success path | The client address is taken from the header only when the previous hop is a trusted proxy |
| Alternate/failure paths | A forged header from outside is ignored |
| Data effects | Addresses in `audit_events`, `user_sessions` |
| Security classification | Personal data (confidential) |
| Audit requirement | Correct addresses on every event |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | Load balancer at hosting |
| Acceptance criteria | Changing the header cannot bypass the sign-in limit |
| Test evidence | `common/tests/test_client_ip_and_headers.py` |
| Release risk | Low |

### HIMS-SEC-015

| Field | Record |
|---|---|
| ID and title | HIMS-SEC-015 Admin console only from allowed addresses |
| Business/clinical reason | The console is the most powerful screen; it must not be reachable from the internet (spec 13). Owner: PO |
| Actors | Every console request; `compliance.view`, `compliance.manage` review refusals |
| Preconditions | `HIMS_ADMIN_ALLOWED_NETWORKS` |
| Main success path | Requests from allowed networks reach the console; others get 404 and are counted |
| Alternate/failure paths | Refusals audited once per address and day, reviewable |
| Data effects | `console_access_blocks` |
| Security classification | Security event (internal) |
| Audit requirement | `auth.console_address_refused`, `compliance.console_block.reviewed` |
| Idempotency/concurrency | One row per address, counted |
| Integration dependencies | Firewall rule at hosting (HIMS-OPS-020) |
| Acceptance criteria | Even the sign-in page is unreachable from outside |
| Test evidence | `common/admin/tests/test_console_allow_list.py`, `apps/compliance/tests/test_console_access.py`; manual test Part 18f |
| Release risk | Availability if the list is wrong (setting change) |

### HIMS-SEC-019

| Field | Record |
|---|---|
| ID and title | HIMS-SEC-019 No password, token, code or key ever reaches a log line |
| Business/clinical reason | Logs are widely readable; secrets in them are leaks (spec 13.5). Owner: PO |
| Actors | Every log line, stored provider error and printed message |
| Preconditions | None |
| Main success path | A filter replaces secrets in every line |
| Alternate/failure paths | A new logging path without the filter fails the test |
| Data effects | None |
| Security classification | Credentials (restricted) |
| Audit requirement | None |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | None |
| Acceptance criteria | Signing in, resets, two-factor and invitations leave no secret in any log |
| Test evidence | `common/tests/test_secrets_never_logged.py`, `common/tests/test_log_safety.py` |
| Release risk | Privacy |

### HIMS-SEC-020

| Field | Record |
|---|---|
| ID and title | HIMS-SEC-020 Error text in traces filtered with the same rules as logs |
| Business/clinical reason | Traces leave the server; they must not carry secrets or personal data (spec 13.3). Owner: PO |
| Actors | Every trace span with an error |
| Preconditions | Tracing switched on |
| Main success path | `exception.message` and stack text pass the log filter before export |
| Alternate/failure paths | Unfilterable text is dropped |
| Data effects | None |
| Security classification | Credentials (restricted) |
| Audit requirement | None |
| Idempotency/concurrency | Not applicable |
| Integration dependencies | Trace collector (hosting) |
| Acceptance criteria | A secret in an error never reaches an exported span |
| Test evidence | `common/tests/test_trace_error_text.py`, `common/tests/test_tracing.py`; manual test Part 18n |
| Release risk | Privacy |
