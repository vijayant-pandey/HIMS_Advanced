# Phase 1 Backlog — Foundation and Hospital Onboarding

Spec section 20, Phase 1. **Exit criterion:** a hospital can be configured, staff can be
onboarded, and isolation is demonstrably enforced.

Each row becomes a GitHub Issue using `.github/ISSUE_TEMPLATE/feature_request.md`.
**Done** means implemented with automated tests in this repository. Every item still has to go
through PR review and the QA gates before it counts as released (spec 35.1).

## EPIC HIMS-PLAT — Platform foundation

| ID | Ticket | Status |
|---|---|---|
| HIMS-PLAT-001 | Repository layout per spec 8; Django/DRF/Celery project; settings per environment | Done |
| HIMS-PLAT-002 | Environment startup guard (local cannot reach managed DB; DB secret must match environment) | Done |
| HIMS-PLAT-003 | RFC 9457 problem responses, field-level validation errors | Done |
| HIMS-PLAT-004 | Request/correlation ID: middleware, logs, audit, outbox, Celery propagation | Done |
| HIMS-PLAT-005 | Structured JSON logging with deployment/environment/release fields | Done |
| HIMS-PLAT-006 | Idempotency-Key support (replay, conflict, concurrent duplicates) | Done |
| HIMS-PLAT-007 | Transactional outbox, SKIP LOCKED dispatcher, consumer dedup (ADR-012) | Done |
| HIMS-PLAT-008 | Optimistic concurrency (`version`) for editable configuration records | Done |
| HIMS-PLAT-009 | Health endpoints (live/ready) | Done |
| HIMS-PLAT-010 | OpenAPI contract generated and validated; frontend types generated from it | Done |
| HIMS-PLAT-011 | Backend container image (non-root, single image for all roles) | Done |
| HIMS-PLAT-012 | Hash-locked Python lockfile (pip-tools or uv) | To do |
| HIMS-PLAT-013 | Pin GitHub Actions to commit SHAs; least-privilege tokens per job | To do |
| HIMS-PLAT-014 | Outbox and idempotency retention/archival jobs and runbook | Partial (idempotency purge done) |
| HIMS-PLAT-015 | Route-level code splitting in the SPA (current bundle > 500 kB) | To do |
| HIMS-PLAT-016 | OpenTelemetry tracing for API, Celery and outbound HTTP | To do |
| HIMS-PLAT-017 | Django admin operations console: RBAC-gated, audited, no deletion (ADR-016) | Done |
| HIMS-SEC-015 | Console network restriction (IP allow-list/VPN) before enabling outside local | To do |
| HIMS-OPS-010 | Static files for admin/API docs in managed environments (WhiteNoise or S3/CloudFront) | To do |

## EPIC HIMS-ORG — Organization and facilities

| ID | Ticket | Status |
|---|---|---|
| HIMS-ORG-001 | Organization model (one per deployment) + `provision_organization` command (ADR-009) | Done |
| HIMS-ORG-002 | `GET/PATCH /organization/` with versioning and audit | Done |
| HIMS-FAC-001 | Facilities API: list/create/retrieve/update, scoped visibility, audit | Done |
| HIMS-FAC-002 | Departments API: create within facility scope, inactive-facility guard | Done |
| HIMS-FAC-003 | Facility admin UI (list + create with idempotency) | Done |
| HIMS-FAC-004 | Location hierarchy: building → floor → ward/unit → room → bed (config only; allocation is Phase 3) | To do |
| HIMS-ORG-003 | Hospital-specific numbering schemes (MRN, encounter, invoice, claim) | To do |
| HIMS-ORG-004 | Feature flags per organization/country/facility | To do |

## EPIC HIMS-IAM — Identity and access

| ID | Ticket | Status |
|---|---|---|
| HIMS-IAM-001 | Custom user (UUID, case-insensitive email), Argon2, password policy | Done |
| HIMS-IAM-002 | Session login/logout/me, CSRF, rate limiting, non-enumerating errors, audit | Done |
| HIMS-IAM-003 | Invitation and account activation (consumes `staff.member.created`) | To do |
| HIMS-IAM-004 | Password reset (non-enumerating, time-limited single-use tokens) | To do |
| HIMS-IAM-005 | MFA (TOTP/WebAuthn) mandatory for privileged roles | To do |
| HIMS-IAM-006 | Invalidate all sessions on suspension/termination/password change | To do |
| HIMS-IAM-007 | Step-up reauthentication for sensitive actions | To do |
| HIMS-IAM-008 | Enterprise SSO (OIDC/SAML) — decision in spec 36 | To do |
| HIMS-IAM-009 | Scoped RBAC: catalog, roles, facility/department assignments, default deny, escalation guard (ADR-015) | Done |
| HIMS-IAM-010 | Patient-relationship scope (treating team / encounter) | To do (Phase 2) |
| HIMS-IAM-011 | Break-glass emergency access with reason, audit and review | To do (Phase 2) |
| HIMS-IAM-012 | Periodic access-review report | To do |
| HIMS-IAM-013 | Role and access-management UI | To do |

## EPIC HIMS-STAFF — Staff and credentials

| ID | Ticket | Status |
|---|---|---|
| HIMS-STAFF-001 | Staff members, department assignments, qualifications, credentials (spec 9.4) | Done |
| HIMS-STAFF-002 | Controlled specialty/qualification catalogs (starter set — clinical informatics to own) | Done |
| HIMS-STAFF-003 | Credential verification with segregation of duties | Done |
| HIMS-STAFF-004 | Termination/suspension disables login | Done |
| HIMS-STAFF-005 | Credential document upload (S3, scanning, signed URLs) | To do |
| HIMS-STAFF-006 | Credential expiry alerts (scheduled job + notifications) | To do |
| HIMS-STAFF-007 | Staff detail/onboarding UI | Partial (list + search done) |
| HIMS-STAFF-008 | Department-scoped staff directory visibility | To do |

## EPIC HIMS-SEC / HIMS-AUD — Security and audit

| ID | Ticket | Status |
|---|---|---|
| HIMS-AUD-001 | Append-only audit events with DB trigger; audit search for auditors, itself audited (ADR-013) | Done |
| HIMS-AUD-002 | Access-denied events recorded outside rolled-back transactions | Done |
| HIMS-SEC-010 | Audit tamper evidence (hash chain or S3 Object Lock export) | To do |
| HIMS-SEC-011 | Threat model and risk assessment (spec 23) | To do |
| HIMS-SEC-012 | Security headers/CSP for the SPA (CloudFront response headers) | To do |
| HIMS-SEC-013 | Upload validation/malware scanning service | To do |
| HIMS-SEC-014 | Trust `X-Forwarded-For` only from the ALB for audit IPs | To do |

## EPIC HIMS-OPS — Delivery and operations

| ID | Ticket | Status |
|---|---|---|
| HIMS-OPS-001 | PR CI: lint, types, migrations, tests on PostgreSQL, contract drift, audits, image build, secret scan | Done (workflow written; runs once the repo is on GitHub) |
| HIMS-OPS-002 | GitHub Organization, branch rulesets (`main`, `develop`), CODEOWNERS teams | To do (needs org owner) |
| HIMS-OPS-003 | Terraform modules (network, ecs-service, rds, redis, s3, kms, secrets, monitoring) — Stage B | To do |
| HIMS-OPS-004 | Alarms + runbooks: API errors/latency, DB, queue age, outbox dead/lag | To do |
| HIMS-OPS-005 | Deploy-to-Development workflow with OIDC; build-once promote-many to QA/Staging/Prod | To do |
| HIMS-OPS-006 | Migration release job with lock; per-customer schema version tracking | To do |
| HIMS-OPS-007 | Separate DB roles (runtime / migration / read-only / break-glass); runtime lacks TRUNCATE on audit | To do |
| HIMS-OPS-008 | Customer provisioning automation in the control plane | To do |
| HIMS-OPS-009 | Backup/restore drill with audit and relationship verification | To do |

## Later phases (epics only; P0 design required before build — spec 26)

Phase 2 Patient/MPI and outpatient · Phase 3 ADT, beds, nursing, diet · Phase 4 Medication,
pharmacy, eMAR, lab, radiology · Phase 5 Insurance (Stedi, India TPAs) and revenue cycle ·
Phase 6 Portal, FHIR/ABDM, PACS/LIS, performance and go-live.
