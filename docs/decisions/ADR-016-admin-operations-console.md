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
MFA on console sign-in (HIMS-IAM-005), IP allow-listing or VPN-only access (HIMS-SEC-015, **done
2026-11-09**: `HIMS_ADMIN_ALLOWED_NETWORKS`; [console allow-list](../workflows/console-allow-list.md);
the firewall layer comes with hosting, HIMS-OPS-020), and
static-file serving for admin assets (HIMS-OPS-010, **done 2026-11-08**: collected at image build
and served by the app with WhiteNoise; [static files](../workflows/static-files.md)).

## Consequences
"Full control" means full control of configuration and operational records, within the
guarantees the specification requires. Clinical and financial domains added later must register
their admins on the same base classes and route state transitions through their services, never
through raw field edits.

## Update 2026-10-27: full coverage is enforced (HIMS-PLAT-018)
The product owner asked that everything be manageable in the console. A test
(`common/admin/tests/test_admin_coverage.py`) now fails when any model is not registered, either on
its own page or as an inline section of its parent. The only deliberate exception is two-factor
backup codes (secret hashes); the device page shows how many remain. The same test opens every
console list and add page. Added at the same time: "Send password reset link" on users, bed status
changes (all staff-settable states, reason required) on the bed page, and Facility → Building →
Floor → Ward → Room → Bed sections on each parent page. Inline edits now also bump `version`.

## Update 2026-10-28 (HIMS-FAC-006)
Departments and facilities follow the same "close in order" rules in the console as in the app
(`Department.clean` / `Facility.clean`). A department with staff posted, access limited to it,
or active wards cannot be set to inactive, and the console shows the same plain-language message.

## Update 2026-11-09 (HIMS-SEC-015): address allow-list, and what the app had but the console did not
- **Address allow-list.** Every console page, the sign-in page included, answers only addresses in
  `HIMS_ADMIN_ALLOWED_NETWORKS` (real client address, ADR-022). Others get the same "Not found" as a
  missing page. A developer PC defaults to this computer only; a hosted environment with the console
  on refuses to start without a list, or with one that lets every address in. Refusals are counted
  per day and address, audited once, reviewable. The list is a server setting on purpose: what
  protects the console is not editable through it. Firewall layer at hosting (HIMS-OPS-020).
  Details: [console allow-list](../workflows/console-allow-list.md).
- **Console parity check.** Everything the app can do was compared with the console. Added, each
  through the same service as the app (same rules, same audit): dismissing a failed background
  event with a typed reason, and the health summary on the Outbox events list (HIMS-PLAT-014);
  "Send a test message" (HIMS-NOTIF-001); "Download as CSV" on an access review (HIMS-IAM-012)
  and "Download selected events as CSV" for auditors (HIMS-AUD-003), both after "confirm it's you";
  and a **Security status** page (top bar, for `compliance.view`): browser protection, where the
  console may be used from, and the database-user checks (HIMS-SEC-012/014, HIMS-OPS-007).

## Update 2026-11-09 (HIMS-FAC-008): bed board, bed history and access review schedule
- **Beds → Bed board**: each ward's beds by status for one facility, with the unavailable beds and
  their reason; the same visibility as the app's Bed board.
- **Status history** section on each bed's page and a **Bed status changes** list; read-only, the
  database refuses changes (append-only table `bed_status_changes`).
- Console parity check repeated: the one thing the app showed and the console did not was **when
  the next access review is due**; the Access reviews list now shows it.
- Every console save now tells the record who is saving (`_hims_actor`), so records that keep
  their own history (bed status) name the person.

## Update (2026-11-09, Hospital setup group)

The console gained **Equipment** and **Equipment service records** (status and visits go through the app's rules; existing visits are read-only), **Message templates** (same checks as the app, confirm-it's-you, and an action to go back to the standard wording) and the **letterhead** fields on the hospital's page, with a logo preview served through a console page because files have no public address. A check of what #42 and #43 added found nothing else missing.
