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
| [022](ADR-022-browser-protection-and-client-address.md) | Browser protection headers and real client addresses | Proposed |
| [023](ADR-023-confirm-before-sensitive-actions.md) | Confirm before sensitive actions | Proposed |
| [024](ADR-024-rotas-no-overlap-in-the-database.md) | Rotas and leave: shifts as instants, overlaps refused by the database | Proposed |
| [025](ADR-025-backups-and-restore-drills.md) | Backups and restore drills checked against an inventory taken in the same snapshot | Proposed |
| [026](ADR-026-separate-database-users.md) | Separate database users, with rights derived from the database and the data dictionary | Proposed |
| [027](ADR-027-hosting-on-oracle-cloud.md) | Host on Oracle Cloud (free offering) at the end of the build, instead of AWS | On hold: Oracle needs a payment card (see 034) |
| [028](ADR-028-message-wording-and-letterhead.md) | Editable message wording with fixed placeholders; letterhead added at delivery | Proposed |
| [029](ADR-029-leave-balances-worked-out.md) | Leave balances are worked out, never stored | Proposed |
| [030](ADR-030-retention-purge-and-legal-hold.md) | Retention purge limited to housekeeping records, with waiting periods and legal holds | Proposed |
| [031](ADR-031-performance-targets-and-volume-check.md) | Response-time targets per screen, an index check that follows the code, and a volume check on a throw-away copy | Proposed |
| [032](ADR-032-requirement-ids-and-contract-docs.md) | Ticket IDs as requirement IDs; endpoint contracts generated from the code | Proposed |
| [033](ADR-033-session-limits-and-sign-in-pause.md) | Session limits background refreshes cannot defeat, and a sign-in pause per account | Proposed |
| [034](ADR-034-free-hosting-without-a-card.md) | A free Development environment on a host that needs no payment card (puts ADR-027 on hold) | Proposed |
| [035](ADR-035-supplier-support-access.md) | Supplier support access, the "locked box": ask, hospital approves, emergency at once, ends by itself, every request audited | Proposed |
| [036](ADR-036-patient-id-numbers.md) | Patient ID numbers: encrypted, masked, found by a keyed fingerprint; one-per-person numbers refused on a second patient | Proposed |
