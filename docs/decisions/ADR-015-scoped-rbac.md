# ADR-015: Scoped, time-bounded RBAC with default deny

**Status:** Proposed. Clinical roles need clinical governance approval of the permission matrix
(spec 26.4). **Owner:** Security.

## Decision
- Permission codenames are defined in code (`apps/access_control/catalog.py`) and synced to the
  `permissions` table after each migration. Removed codenames are deactivated, never deleted.
- A `RoleAssignment` grants a role to a user **organization-wide**, **for one facility** or **for
  one department in a facility**. It is valid for a time window and revoked rather than deleted,
  so access history is preserved for access reviews.
- **Default deny.** Every DRF view declares `required_permissions` per action, and anything not
  declared is refused. A test fails the build if a view forgets to declare them.
  Facility-scoped views filter querysets to the facilities the grant covers, so out-of-scope
  records return 404 instead of revealing that they exist.
- **No escalation.** A user can only grant permissions they hold themselves at the target scope,
  and cannot revoke their own assignments.
- **Separation of duties.** The organization-administrator role excludes `audit.view`. Auditors
  are created at provisioning. Credential verifiers cannot verify their own credentials.
- There is no superuser flag that bypasses authorization.

## Next
Patient-relationship scope (treating team, encounter) and break-glass emergency access, built with
the patient domain (HIMS-IAM-010, HIMS-IAM-011); periodic access-review reports (HIMS-IAM-012).
