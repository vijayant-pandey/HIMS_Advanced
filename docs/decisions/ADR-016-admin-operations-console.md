# ADR-016: Django admin as an RBAC-gated, audited operations console

**Status:** Proposed — needs Security approval before enabling outside local. **Owner:** Security
+ Engineering lead.

## Context
The product owner wants full operational control through Django admin. Stock Django admin uses
`is_staff`/`is_superuser`, writes directly to models (bypassing domain services), allows
deletion, and does not write HIMS audit events. Spec 8.1 warns that admin forms must not be what
protects critical rules, spec 13.2 requires least privilege, and spec 28.2 forbids erasing
signed/financial facts.

## Decision
- The admin site is replaced by `HimsAdminSite`. Entry requires the RBAC permission
  `platform.admin_console`, which the organization-administrator role holds. Auditors (`audit.view`)
  can enter but only see the audit log. There is no `is_staff`/`is_superuser`.
- **Every add/change is audited** (`admin.<model>.created|updated`, with before/after values) in
  the same transaction. Versioned records get their version bumped, so API clients holding stale
  copies receive 409.
- **Deletion is disabled everywhere.** Records are deactivated, revoked or corrected instead.
- **Domain rules are reused, not duplicated.** Role grants and revocations go through
  `access_control.services` (scope rules, escalation guard). Staff creation and employment-status
  changes trigger the same side effects as the API (login disabled, outbox events). Credential
  verification uses the service, including its self-verification guard. Department rules live
  in `Department.clean()`.
- **Separation of duties holds in the console.** Administrators cannot see or grant audit
  access, cannot add permissions they do not hold to a role, cannot edit system roles, and
  cannot alter audit events (the database rejects it anyway).
- Console sign-in is audited and locks out an IP for 15 minutes after 5 failed attempts.
- The console is exposed only where `HIMS_ENABLE_ADMIN=true`: on by default locally, off by
  default in managed environments.

## Before enabling in Development/QA/Staging/Production
MFA on console sign-in (HIMS-IAM-005), IP allow-listing or VPN-only access (HIMS-SEC-015), and
static-file serving for admin assets (HIMS-OPS-010).

## Consequences
"Full control" means full control of configuration and operational records, within the
guarantees the specification requires. Clinical and financial domains added later must register
their admins on the same base classes and route state transitions through their services, never
through raw field edits.
