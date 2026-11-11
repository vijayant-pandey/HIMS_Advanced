# Requirement records: messages and compliance

Spec sections 4.23, 4.25, 13, 23. Format: [README](README.md). Endpoints:
[messages](../architecture/api-and-integrations/endpoints/notifications.md),
[compliance and security](../architecture/api-and-integrations/endpoints/compliance.md).

### HIMS-NOTIF-001

| Field | Record |
|---|---|
| ID and title | HIMS-NOTIF-001 Messages: email and SMS, delivery log, retries, hidden secrets, Messages page |
| Business/clinical reason | Invitations, resets and alerts must arrive, and failures must be visible (spec 4.23). SMS stays printed on the console until the PO chooses a gateway (HIMS-NOTIF-002). Owner: PO |
| Actors | Services send messages; a scheduled job retries failures; `notifications.view`, `notifications.manage` |
| Preconditions | Email settings (console locally; HIMS-OPS-011 at hosting) |
| Main success path | Each message is logged and tried at once; the log shows it as sent |
| Alternate/failure paths | Provider failure never undoes the action that caused it: the message is retried after 5, 15, 60 and 240 minutes, then shown as failed with Send again; secrets in links never appear in the log |
| Data effects | `notifications` |
| Security classification | Personal data (confidential): addresses; links masked |
| Audit requirement | `notification.retried`, `notification.test_sent` |
| Idempotency/concurrency | Each message is one row; retries update that row, so it is never sent twice after success |
| Integration dependencies | Email provider; SMS gateway later; timeouts 20 s |
| Acceptance criteria | No message is lost if the provider is down (it stays failed and retried); nothing secret is shown on the page |
| Test evidence | `apps/notifications/tests/test_notifications.py` |
| Release risk | Operational (messages delayed). Rollback: Send again |

### HIMS-NOTIF-003

| Field | Record |
|---|---|
| ID and title | HIMS-NOTIF-003 Hospital-editable message wording (per-patient opt-out moved to HIMS-NOTIF-004, Phase 2) |
| Business/clinical reason | Hospitals word their own messages and languages. Owner: PO |
| Actors | `notifications.view`, `notifications.templates.manage` |
| Preconditions | Standard wording seeded |
| Main success path | Edit subject and text with placeholders; preview with made-up values; reset to standard |
| Alternate/failure paths | Unknown or missing required placeholders → 400; stale version → 409 |
| Data effects | `message_templates` |
| Security classification | Configuration (internal) |
| Audit requirement | `notification.template.updated`, `notification.template.reset` |
| Idempotency/concurrency | `version` |
| Integration dependencies | None |
| Acceptance criteria | A link placeholder cannot be removed from an invitation |
| Test evidence | `apps/notifications/tests/test_message_templates.py`; manual test Part 18j |
| Release risk | Low. Rollback: reset to standard |

### HIMS-COMP-001

| Field | Record |
|---|---|
| ID and title | HIMS-COMP-001 US: HIPAA Security Rule risk analysis, policies and procedures, business associate list |
| Business/clinical reason | Required before a US hospital goes live. Owner: LEGAL (approved for now 2026-11-08; counsel review pending) |
| Actors | `compliance.view`, `compliance.manage` |
| Preconditions | US deployment |
| Main success path | Compliance page lists the HIPAA requirements with status, evidence and review dates |
| Alternate/failure paths | India-only requirements hidden in a US hospital and the other way round |
| Data effects | `compliance_requirements` |
| Security classification | Compliance evidence (internal) |
| Audit requirement | `compliance.requirement.updated` |
| Idempotency/concurrency | `version` |
| Integration dependencies | None |
| Acceptance criteria | Every requirement has an owner, a status and a next review date |
| Test evidence | `apps/compliance/tests/test_compliance.py`; documents in `docs/compliance/` |
| Release risk | Legal (go-live blocked until counsel signs off) |

### HIMS-COMP-002

| Field | Record |
|---|---|
| ID and title | HIMS-COMP-002 India: DPDP Act 2023 and Rules 2025 assessment, privacy notice, consent and breach-notice procedure |
| Business/clinical reason | Required for Indian hospitals. Owner: LEGAL (approved for now 2026-11-08) |
| Actors | `compliance.view`, `compliance.manage` |
| Preconditions | India deployment |
| Main success path | DPDP requirements tracked with status and evidence; breach-notice deadlines on incidents |
| Alternate/failure paths | As HIMS-COMP-001 |
| Data effects | `compliance_requirements` |
| Security classification | Compliance evidence (internal) |
| Audit requirement | `compliance.requirement.updated` |
| Idempotency/concurrency | `version` |
| Integration dependencies | None |
| Acceptance criteria | As HIMS-COMP-001 |
| Test evidence | `apps/compliance/tests/test_compliance.py` |
| Release risk | Legal |

### HIMS-COMP-003

| Field | Record |
|---|---|
| ID and title | HIMS-COMP-003 India: ABDM health data management policy and IT Act security practices |
| Business/clinical reason | Required before ABDM integration. Owner: LEGAL (approved for now 2026-11-08) |
| Actors | `compliance.view`, `compliance.manage` |
| Preconditions | India deployment |
| Main success path | ABDM and IT Act requirements tracked |
| Alternate/failure paths | As HIMS-COMP-001 |
| Data effects | `compliance_requirements` |
| Security classification | Compliance evidence (internal) |
| Audit requirement | `compliance.requirement.updated` |
| Idempotency/concurrency | `version` |
| Integration dependencies | ABDM later (Phase 6) |
| Acceptance criteria | As HIMS-COMP-001 |
| Test evidence | `apps/compliance/tests/test_compliance.py` |
| Release risk | Legal |

### HIMS-COMP-004

| Field | Record |
|---|---|
| ID and title | HIMS-COMP-004 Both countries: retention schedule, incident response, access-control policy, vendor list |
| Business/clinical reason | Hospitals must be able to show these documents and run incidents to their legal deadlines. Owner: LEGAL |
| Actors | `compliance.view`, `compliance.manage`; anyone with `compliance.view` may report an incident |
| Preconditions | None |
| Main success path | Report an incident; the required notices and their deadlines are listed; record each notice as sent |
| Alternate/failure paths | A notice not part of the incident → 400; overdue notices highlighted |
| Data effects | `security_incidents`, `security_incident_notifications` |
| Security classification | Compliance evidence (restricted) |
| Audit requirement | `compliance.incident.reported`, `compliance.incident.updated`, `compliance.incident.notification_recorded` |
| Idempotency/concurrency | `version` on incidents |
| Integration dependencies | None |
| Acceptance criteria | Every incident shows each country's deadline |
| Test evidence | `apps/compliance/tests/test_compliance.py`; manual test Part 17 |
| Release risk | Legal |

### HIMS-COMP-005

| Field | Record |
|---|---|
| ID and title | HIMS-COMP-005 Threat model and risk register (spec 23) |
| Business/clinical reason | Risks are tracked with owners and treatments. Owner: PO, LEGAL |
| Actors | `compliance.view`, `compliance.manage` |
| Preconditions | None |
| Main success path | Add and update risks with likelihood, impact, owner and treatment |
| Alternate/failure paths | Stale version → 409 |
| Data effects | `compliance_risks` |
| Security classification | Compliance evidence (restricted) |
| Audit requirement | `compliance.risk.created`, `compliance.risk.updated` |
| Idempotency/concurrency | `version` |
| Integration dependencies | None |
| Acceptance criteria | Open risks show on the compliance summary |
| Test evidence | `apps/compliance/tests/test_compliance.py`; `docs/compliance/threat-model.md` |
| Release risk | Low |

### HIMS-COMP-006

| Field | Record |
|---|---|
| ID and title | HIMS-COMP-006 Retention purge with legal hold |
| Business/clinical reason | Records are kept as long as the law requires and no longer; a legal hold stops deletion (DPDP, HIPAA). Owner: LEGAL sets the periods |
| Actors | `compliance.view`, `compliance.manage`; daily purge job |
| Preconditions | Periods set by the hospital (nothing is deleted until then) |
| Main success path | Set periods; shorter ones wait 7 days; the daily job deletes in batches what is older and not on hold; each run is recorded |
| Alternate/failure paths | Records on legal hold are skipped; the audit log is never purged here (HIMS-COMP-007) |
| Data effects | `retention_rules`, `legal_holds`, `retention_purge_runs`; deletes from `user_sessions`, `notifications` and other listed tables |
| Security classification | Compliance evidence (restricted) |
| Audit requirement | `compliance.retention.period_changed`, `compliance.retention.period_applied`, `compliance.retention.purge_run`, `compliance.legal_hold.placed`, `compliance.legal_hold.released` |
| Idempotency/concurrency | One purge at a time; repeating finds nothing new |
| Integration dependencies | None |
| Acceptance criteria | Nothing on hold is ever deleted; a shortened period does not delete for 7 days |
| Test evidence | `apps/compliance/tests/test_retention.py`; manual test Part 18p |
| Release risk | Data loss if periods are wrong (7-day wait, backups). Rollback: restore from backup |
