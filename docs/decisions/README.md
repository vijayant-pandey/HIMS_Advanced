# Architecture Decision Records

Format: context, decision, alternatives, consequences, owner, review date (spec section 22).
Status values: **Accepted** (approved, in force), **Proposed** (implemented as the working
default, awaiting the named approver), **Superseded**.

| ADR | Title | Status |
|---|---|---|
| [001](ADR-001-modular-monolith.md) | Modular monolith before microservices | Accepted (spec 22) |
| [002](ADR-002-postgresql-authoritative.md) | PostgreSQL as the authoritative database | Accepted (spec 22) |
| [003](ADR-003-dedicated-deployment-per-organization.md) | Dedicated deployment and database per hospital organization | Accepted (spec 22) |
| [004](ADR-004-redis-not-source-of-truth.md) | Redis is not the source of truth | Accepted (spec 22) |
| [005](ADR-005-transactional-outbox.md) | Transactional outbox for critical async workflows | Accepted (spec 22) |
| [006](ADR-006-provider-neutral-insurance.md) | Provider-neutral insurance integration layer | Accepted (spec 22) |
| [007](ADR-007-interoperability-boundary.md) | Interoperability as an explicit boundary | Accepted (spec 22) |
| [008](ADR-008-auditability.md) | Clinical and financial records require auditability | Accepted (spec 22) |
| [009](ADR-009-single-organization-per-deployment.md) | One organization row per deployment; provisioning instead of a create API | Proposed |
| [010](ADR-010-celery-broker.md) | Celery broker: Redis now, SQS evaluated before production | Proposed |
| [011](ADR-011-browser-session-authentication.md) | Server-side session authentication for the browser SPA | Proposed |
| [012](ADR-012-outbox-dispatcher.md) | Outbox dispatcher and consumer deduplication | Proposed |
| [013](ADR-013-audit-log-storage.md) | Append-only audit log enforced in PostgreSQL | Proposed |
| [014](ADR-014-runtime-versions.md) | Runtime and toolchain versions | Proposed |
| [015](ADR-015-scoped-rbac.md) | Scoped, time-bounded RBAC with default deny | Proposed |
| [016](ADR-016-admin-operations-console.md) | Django admin as an RBAC-gated, audited operations console | Proposed |
| [017](ADR-017-hosting-and-branch-promotion.md) | Interim hosting on Render + Vercel; branch-per-environment promotion | Proposed |
| [018](ADR-018-two-factor-sign-in.md) | Two-factor sign-in with authenticator apps (TOTP) | Proposed |
| [019](ADR-019-feature-flags.md) | Feature settings per hospital, country and facility | Proposed |
| [020](ADR-020-document-storage.md) | Storing staff documents; licence expiry alerts | Proposed |
| [021](ADR-021-tracing.md) | OpenTelemetry tracing, off by default and PHI-safe | Proposed |
