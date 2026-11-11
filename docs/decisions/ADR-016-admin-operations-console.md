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

## Update (2026-11-09, Staff group)

The console gained **Clinical privileges**, **Staff privileges**, **Staffing requirements** with a **Staffing gaps** page, **Staffing gap alerts**, **Leave entitlements** and **Leave balance adjustments**, an action to approve leave over the balance, the leave year on the hospital's page, and read-only privilege and balance sections on the staff page. These sections are read-only fields rather than inlines, so saving the staff page needs nothing extra. Everything goes through the app's rules; a refusal shows on the form.

## Update (2026-11-10, Security filters group)

**Security status** gained "Virus scanning of uploads" and "Traces". **Staff documents** shows how each
file was checked, filters by it, blocks opening an infected one, and has the action "Check selected
documents for viruses now". A file uploaded in the console (staff document, logo) is checked like one
uploaded in the app, with the refusal on the form. A check of what #45 added found nothing missing.

## Update (2026-11-10, passkeys)

The console gained **Passkeys**: who has which, never the key itself, and the action "Remove selected
passkeys" for a lost device (after "confirm it's you"). The console's own sign-in still asks for the
authenticator code. A check of what #46 added found nothing missing.

## Update (2026-11-10, retention purge)

The console gained **Retention rules** (each kind's period, the shorter one waiting, what a purge would
delete now and what holds keep; change or cancel with the same rules as the app), **Legal holds** (place
on chosen kinds and optionally one person; release with a reason; never deleted) and **Retention purge
runs** (append-only history and **Run the purge now**). Each change asks "confirm it's you" first. A
check of what #47 added found nothing missing.

**Update 2026-11-10 (HIMS-DATA-002, HIMS-OPS-017, HIMS-QA-003):** Performance → **Performance
checks** lists every index check and response-time measurement (read-only evidence, results per query
or screen) with **Run the index check now** for holders of `platform.performance.manage`, the same
service as the app's Performance screen. The response-time check now also times the console's lists
of the six largest tables; it found the "By department" filters and department columns looking up
each department's facility one query at a time, fixed with `DepartmentListFilter` and
`list_select_related` (rota, leave, minimum staffing, gap alerts, role assignments, wards, clinical
privileges). The lists of the five largest tables (audit events, messages, background events,
sign-ins, issued numbers) took up to 1.9 s at hospital size: they now count up to 10,000 ("More than
10,000"), skip Django's second full count, and filter dates with Today / Past 7 days / This month
instead of the date bar (`LargeTableAdminMixin`); the audit list's record type, the messages' kind
and the background events' type moved from filters to the search box. The console now has its own browser tests (`05-admin-console.spec.ts`, and the US
hospital's console in `e2e/us`). A check of what #48 added (retention rules with their preview, legal
holds, purge runs with Run now) found nothing missing.

**Update (2026-11-11, HIMS-DOC-001):** the console has an **API endpoints** page (link at the top right, for holders of `access.roles.view`): every endpoint, who may call it, whether it needs "confirm it's you", what it records and its requirement, read from the same code as the app's Access page tab. A check of what #49 added (performance checks with Run the index check now, the large-list counting, the department filters) found nothing missing: the response-time and volume checks run from the command line only, as on the app's Performance screen.

**Update (2026-11-11, HIMS-SEC-011):** the console's **Security status** page also shows the encryption key status (how many stored secrets still need an older key) and the Phase 1 security review (findings and the ten spec 13.5 tests), the same as the Compliance page's Security review tab. The console sign-in shares the per-account pause after 10 wrong passwords, and console sessions follow the same idle and 12-hour limits. A check of what #50 added (the API endpoints page) found nothing missing. Key rotation is a command (`rotate_encryption_keys`), not a console button: it is part of changing the keys in the secret store, which happens outside HIMS.

**Update (2026-11-11, HIMS-OPS-020):** the console's **Security status** page shows **Hosting readiness**: this server's settings checked against what any host must give HIMS, the same as the Compliance page tab and `hosting_check`. A check of what #51 added (session limits, the per-account sign-in pause, the encryption key status and the security review) found nothing missing.

**Update (2026-11-11, HIMS-OPS-023):** the console lists the scheduled jobs (**Outbox → Scheduled jobs**): how often each runs and its last run, read-only, the same as the Background jobs page; runs are started by the host's timer (`run_scheduled_jobs`), not from the console. A check of what #52 added (the Hosting readiness section) found nothing missing.
