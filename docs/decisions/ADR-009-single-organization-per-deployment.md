# ADR-009: One organization row per deployment; provisioning instead of a create API

**Status:** Proposed. **Owner:** Architecture. **Review:** before the first customer deployment.

## Context
ADR-003 gives each hospital organization its own deployment and database. Spec section 16 lists
`POST /api/v1/organizations/` for "hospital setup", while section 7.2 assigns organization
onboarding to the control plane. Section 9 places `organization_id` on organization-owned tables.

## Decision
1. Each deployment database holds exactly one `organizations` row, enforced by a unique
   `singleton` constraint. Its `deployment_id` must equal the server's `HIMS_DEPLOYMENT_ID`.
2. The organization is created by provisioning automation (`manage.py provision_organization`),
   invoked by the control plane / release job, not by a public API. Hospital administrators
   view and update it through `GET/PATCH /api/v1/organization/`.
3. Organization-owned tables keep an `organization_id` foreign key as defence-in-depth and so that
   exports and restores are self-describing. It is **not** the isolation mechanism: isolation comes
   from the dedicated deployment, database credentials, cache prefix and queue names.
4. The organization is always resolved from server configuration, never from client input
   (spec 7.4).

## Alternatives
- Public `POST /organizations/`: lets an API caller create tenants inside a data plane. This
  conflicts with section 7.2 and would need an unauthenticated or super-user bootstrap path.
- Dropping `organization_id`: simpler, but loses self-describing rows and makes a future change
  to a shared-cluster tier (spec 7.3) harder.

## Consequences
- The section 16 "Hospital setup" endpoint is delivered as provisioning plus `PATCH /organization/`.
- Cross-organization queries are impossible by construction, which is the intended behaviour
  (spec 7.6, 26.5).
