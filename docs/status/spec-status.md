# HIMS — Implementation Status vs Specification v2

Tracks delivery against [HIMS_Architecture_Specification_v2.MD](../../HIMS_Architecture_Specification_v2.MD).
The specification is the source of truth and is **not** edited by this tracker.
Updated after every completed work item.

**Last updated:** 2026-10-30 · **Overall:** ~23% of the full specification · **Phase 1:** application ~100% (queue finished; rest blocked), infrastructure/hosting part ~10% (spec 20: Phase 1 also includes infrastructure automation, observability and deployment environments, deferred by PO choice until coding is done)

**Legend**
- ✅ Done: implemented and covered by automated tests
- 🟡 Partial
- ⬜ Not started
- 🔓 Can be built now, with no external dependency
- 🔒 Blocked (the blocker is named)

**Who unblocks what**

| Code | Meaning |
|---|---|
| **PO** | You (product owner): decisions, approvals |
| **CLIN** | Clinical governance: doctors, nurses, pharmacists |
| **LEGAL** | Legal/compliance |
| **AWS** | AWS account and cloud stage (deferred by choice until coding is done) |
| **GH** | GitHub Organization/remote |
| **PAYER** | Stedi, Indian insurers/TPAs |
| **VENDOR** | PACS/LIS/drug-database vendors and licences |

---

## Next work queue: dependency-free, in recommended order

| # | Item | Spec § | Ticket | Status |
|---|---|---|---|---|
| 0 | UI theme selector (white & blue/red/green, minimal black & white) across launcher, apps and admin | 15.2 | HIMS-UI-001 | ✅ (extended to 10 themes in HIMS-UI-002) |
| 1 | Staff invitation and account activation (email to console locally) | 4.4 | HIMS-IAM-003 | ✅ |
| 2 | Password reset (non-enumerating, single-use tokens) | 4.4, 13.1 | HIMS-IAM-004 | ✅ |
| 2b | Hospital roles catalog: designations junior→senior (IN/US), departments/specialties, qualifications, administrative system roles, RBAC document | 3, 4.2, 4.3, 26.4 | HIMS-STAFF-009 | ✅ |
| 2c | Friendly "no access yet" page instead of "Permission denied" for new users (reference number is already recorded in the audit log as `access.denied` → request_id) | 15, 13.4 | HIMS-UI-002 | ✅ Done: welcome page records `access.none_assigned` with its reference; friendlier 403 with reference; 10 themes; compact modern design |
| 3 | End all sessions on suspension/termination (password change already ends them) | 13.5 | HIMS-IAM-006 | ✅ Done: session register; all sessions deleted on deactivation, password change/reset and admin "Sign out of all devices"; audited with count and reason; nightly cleanup |
| 4 | MFA (TOTP) for privileged users and the admin console | 4.4, 13.1 | HIMS-IAM-005 | ✅ Done: authenticator-app codes, required for privileged roles (optional for others), QR setup, 10 backup codes, two-step sign-in in app and admin console, encrypted secret, admin reset for lost phones, ADR-018 |
| 5 | Location hierarchy: building → floor → ward → room → bed (configuration) | 4.1, 4.10 | HIMS-FAC-004 | ✅ Done: buildings, floors, wards/units (12 types incl. ICU/NICU/OT), rooms, beds (13 types); bed status rules (available/maintenance/blocked/out of service by staff; reserved/occupied/cleaning reserved for admissions in Phase 3); bulk bed creation; whole-facility tree with bed counts; new **bed manager** role; Locations page; admin console; [design doc](../architecture/data-architecture/locations-and-beds.md) |
| 5b | Screens to add/edit buildings, floors, wards, rooms and beds in the app | 15.1 | HIMS-FAC-005 | ✅ Done: Locations page now has Add building / floor / ward / room, "Add beds" (numbered, with a preview and a clash warning), Edit and deactivate at every level, bed details from the bed dialog, "Hide inactive"; buttons only for people who may change the layout; codes made safe as you type and locked after creation; server messages shown next to the field. Admin console re-checked for items 1–6 (all models covered, test-enforced) |
| 6 | Hospital numbering schemes (MRN, encounter, invoice, claim) | 4.1 | HIMS-ORG-003 | ✅ Done: hospital-wide and per-facility series; prefix, separator, facility code, restart per calendar/financial year or month, digits; never duplicated, no gaps (GST), facility time zone; India GST 16-character check; "continue from previous system" (forward only); issued-number register; India/US defaults; Numbering page with live preview; admin console; [design doc](../architecture/data-architecture/numbering-schemes.md) |
| 6b | Admin console coverage check (items 1–5) | 13, ADR-016 | HIMS-PLAT-018 | ✅ Done: every model manageable in the admin console (test fails if one is missing); added "Send password reset link" (item 2), bed status Maintenance/Blocked with reason (item 5), Facility → Building → Floor → Ward → Room → Bed drill-down (item 5); location codes locked after creation |
| 7 | Feature flags per organization/country/facility | 4.1 | HIMS-ORG-004 | ✅ Done: Features page (whole hospital or per facility, reason required, audited); 3 live features (forgot-password emails, two-factor for all staff, Locations per facility) enforced by the server; 12 planned modules shown as "Coming in Phase N" and locked; country rules (ABDM/India TPAs India-only, Stedi US-only); admin console lists every feature; [ADR-019](../decisions/ADR-019-feature-flags.md). Admin console re-checked for items 1–7 |
| 8 | Staff UI: detail, onboarding, departments, roles and access | 15 | HIMS-STAFF-007, IAM-013 | ✅ Done: Staff page (add staff, status filter, open a person); staff detail page (edit, employment status with sign-out warning, invitation status and send/resend, department postings add/end, qualifications add/verify, licences add/verify with expiry warning, Access tab); Access page (who has access where, remove access; roles with their permissions, create/edit custom roles); new rules: nobody can give themselves access, system roles locked, no granting what you don't hold, role edits versioned and audited. Admin console re-checked for items 1–8 |
| 8b | Departments screen (add/edit/deactivate departments per facility) and facility edit screen (today only list + create in the app) | 4.1, 4.2, 15.1 | HIMS-FAC-006 | ✅ Done: Departments page (by facility and status; staff and ward counts; staff count opens the staff list for that department; add, edit, deactivate, reactivate); Facilities page shows type and active departments and has Edit (address, time zone, phone, status); "close in order" rules for departments and facilities, also in the admin console; [design doc](../architecture/data-architecture/facilities-and-departments.md). Admin console re-checked for items 1–8b |
| 8c | Audit log screen for auditors (search by person, action, date, reference number; today admin console only) | 13.4, 4.25 | HIMS-AUD-003 | ✅ Done: Audit log page for auditors (search by reference number, person, area, event, outcome, dates; plain-language event names; who/where shown by name; before/after details; page links like /audit?request_id=…), **CSV download** (max 5,000 rows, spreadsheet-formula safe, itself audited), clear messages for mistyped filters; admin console audit list now shows "what happened" and "who" in words. Administrators still cannot see it (separation of duties). Admin console re-checked for items 1–8c |
| 8d | Hospital settings screen (name, legal name, default time zone; today admin console only) | 4.1 | HIMS-ORG-005 | ✅ Done (with 8e): Hospital settings page shows name, legal name, country, currency, default time zone, status; Edit (name, legal name, time zone) with version; country and currency stay fixed |
| 8e | Accounts without a staff record (e.g. the first administrator and auditor created at provisioning): list them and manage their access in the app (today admin console only) | 4.4, 15.1 | HIMS-IAM-015 | ✅ Done: Accounts page (everyone who can sign in; staff / not staff; search; status: active, invitation sent, not activated, switched off; roles; two-factor; last sign-in); account page with Access panel, send invitation, reset two-factor, sign out of all devices, switch off/on with reason; **Add account** for people who are not staff (new permission `accounts.manage`, two-factor required); **the last hospital administrator can never be switched off** (Accounts page, admin console, and staff suspension/termination); nobody switches their own account. Admin console re-checked for items 1–8e |
| 8f | Department head, services offered and operating hours (spec 4.2 "Left") | 4.2 | HIMS-FAC-007 | ✅ Done: department page (head chosen from working staff posted there, cleared automatically when their posting or employment ends; services offered, switch on/off, never deleted; weekly opening hours with split sessions, open-24-hours switch, overlap checks, facility time zone); departments list shows head and links to the page; admin console has head, services and hours (same checks, hours changes audited) |
| 8g | Catalog screens: add/edit designations (job titles), specialties and qualification types in the app (today they appear as drop-downs and are managed only in the admin console) | 4.2, 4.3 | HIMS-STAFF-010 | ✅ Done: Job titles & catalogs page (job titles, specialties, qualification types; search; standard vs added by hospital; add, rename, switch off/on; codes never change; switched-off entries leave drop-downs but stay on existing records); new permission `catalogs.manage` (HR/credentialing officer, organization administrator); admin console locks codes and marks console additions |
| 8h | "My sign-ins" on the Security page: see your own open sessions (device, time) and sign out other devices yourself (today only an administrator can do it) | 4.4, 13.5 | HIMS-IAM-016 | ✅ Done: Security page lists your own sign-ins (device such as "Chrome on Windows", time, IP address, "This device"); sign out one other device or all other devices yourself; expired sign-ins are hidden; session secrets are never shown; audited as "Signed out of devices" with reason "signed out by the person" |
| 9 | Credential documents (local storage adapter; S3 later) + expiry alerts | 4.3, 4.22 | HIMS-STAFF-005/006 | ✅ Done: upload a PDF/JPG/PNG (max 10 MB, real type checked from the file) to any licence or qualification; open/download through the app only (permission check, audited, no public link, sandboxed); archive with reason, never deleted; files kept per hospital; **daily expiry alerts** 60/30/7 days before and once expired to HR and the person, each stage once (safe to re-run, catches up); **Licence expiry** page and Staff-page banner; admin console uploads with the same checks; deploy check warns if hosted environments keep files on local disk; [ADR-020](../decisions/ADR-020-document-storage.md). Admin console re-checked for items 1–9 |
| 10 | Audit tamper evidence (hash chain) | 13.4 | HIMS-SEC-010 | ✅ Done: every audit record is **sealed** within a minute into a numbered chain (SHA-256 fingerprint of the record + HMAC-SHA256 link signed with a key kept outside the database, `HIMS_AUDIT_CHAIN_KEYS`, rotatable; production refuses to start without it); **integrity check** daily, on demand (**Audit integrity** page "Check now", admin console button, `manage.py check_audit_log`) finds changed/deleted records, broken or rebuilt links, unknown keys, a chain cut short or rewritten, back-dated records never sealed; results kept append-only and in the audit log; **auditors emailed** on problems; auditors only (administrators cannot see or run it); [design](../architecture/data-architecture/audit-integrity.md), ADR-013 updated. Gaps recorded: HIMS-SEC-016 (copy chain head to S3 Object Lock, 🔒 AWS), HIMS-SEC-017 (background check at ~1M records) |
| 11 | Periodic access-review report | 4.4, 13.2 | HIMS-IAM-012 | ✅ Done: **Access reviews** page. Start a review (snapshot of everyone's current access: person, role, place, last sign-in, account on/off); keep or remove each entry (one or many at once); removing needs a reason and ends the access at once; nobody decides on their own access; complete only when every entry is decided (then locked); cancel with a reason; CSV download for auditors; reviews due every 90 days (`HIMS_ACCESS_REVIEW_INTERVAL_DAYS`), daily reminder email when due or overdue (each sent once); new permissions `access.reviews.view` (auditor, administrator) and `access.reviews.manage` (administrator, two-factor required); admin console: start, keep/remove, complete, cancel, reminders log. Also: the **last administrator's role can no longer be removed** (Access page, review, admin console) |
| 11b | Delegated access: let a person temporarily act with another person's access (e.g. cover during leave), time-limited, with reason and audit (spec 4.4 "delegated access") | 4.4, 13.2 | HIMS-IAM-017 | ✅ Done: **Cover** page. An administrator lends some or all of a person's own access to a colleague for up to 30 days (`HIMS_DELEGATION_MAX_DAYS`), starting now or later, with a reason; the lent access is a time-limited copy of each role (same scope, never longer than the original), so every permission rule works unchanged; it ends by itself, early with a reason, when the original role is removed, or when either account is switched off; nobody arranges cover for themselves, no escalation, auditor access never lent, lent access never lent on and never counts as an administrator; both people emailed; shown on the Access page ("Cover for …"), in access reviews and on each person's Security page; admin console: arrange, view, end. [Design](../architecture/data-architecture/cover-arrangements.md). Gaps recorded: HIMS-IAM-018 clinical delegation (🔒 CLIN), HIMS-IAM-019 self-service cover requests (optional) |
| 12 | Artifact A docs for built domains (ERD, data dictionary) | 28 | HIMS-DATA-001 | ✅ Done: **generated from the code** by `python manage.py data_dictionary`: [data dictionary](../architecture/data-architecture/data-dictionary.md) (44 tables, 447 columns: type, empty allowed, default, allowed values, who sets it, sensitivity, meaning; keys, constraints, indexes, lifecycle and owner per table) and [ERDs](../architecture/data-architecture/erd.md) (all tables + one per domain); CI fails when they are stale, when a table has no lifecycle rule, or when a credential is not classified Secret / personal data not Restricted; [Artifact A index](../architecture/data-architecture/README.md) covers all 12 deliverables of spec 28.1 (ownership, classification and access matrix, lifecycle, index ↔ query patterns, transactions, history model, migrations, catalogs, data flows, synthetic data). Gaps recorded: HIMS-DATA-002 (index check at production-like volume), HIMS-DATA-003 (repeat for each P0 domain, with Phase 2) |
| 13 | Playwright end-to-end tests for built flows | 19.2 | HIMS-QA-001 | ✅ Done: 23 browser tests in real Chrome against a throw-away database (`npm run e2e`): first sign-in with two-factor, wrong password/code, role menus, facility/department/locations/beds/bed status, staff invitation → activation in a second browser → no-access reference → give access, cover, access review, auditor finds the event by reference, integrity check, administrator refused the audit log, keyboard-only menu; **axe accessibility checks** (WCAG 2.1 AA) on every main screen; GitHub workflow `browser-tests` (PRs into development, nightly, on demand; not yet required). **Bugs found and fixed:** backup codes never shown after turning on two-factor; newer link in the same tab stuck on "not valid"; low contrast (current menu item, Green/Orange menu text, info/warning chips); unnamed loading bars. [How-to](../testing/browser-tests.md) |
| 14 | Engineering hygiene: hash-locked lockfile, code splitting, OpenTelemetry (local) | 6.2, 18, 33 | PLAT-012/015/016 | ✅ Done: **hash-locked Python lockfiles** (`requirements/*.in` → `*.txt` with SHA-256 checksums for Windows and Linux, generated by uv; CI and the image install with `--require-hashes`, the image with `--no-deps`; a test fails if a lockfile and its `.in` disagree; pip-audit on both; exact Node `24.18.0` in `.nvmrc`, `backend/.python-version`); **route-level code splitting** (screens load when first opened; first download 1,045 kB → 494 kB, gzip 313 → 153 kB; loading bar; friendly "HIMS was updated, reload" page; CI bundle budget 500 kB); **OpenTelemetry tracing** for API, database, Celery and outbound HTTP, off by default (`HIMS_TRACING_EXPORTER` none/console/otlp), PHI-safe (no query strings, no SQL values, no bodies), API spans carry the reference number and log lines carry `trace_id`; optional local trace viewer (Jaeger) in docker compose; [ADR-021](../decisions/ADR-021-tracing.md), [tracing how-to](../workflows/tracing.md), [dependencies how-to](../workflows/dependencies.md). Gap found and fixed: production access logs no longer contain query strings. Gaps recorded: HIMS-PLAT-019 (send traces to AWS, 🔒 AWS); HIMS-PLAT-013 (pin GitHub Actions) added to the queue as 14b |
| 14b | Pin GitHub Actions to commit SHAs; least-privilege tokens per job (spec 33.6) | 33 | HIMS-PLAT-013 | ✅ Done: all 4 third-party actions pinned to the commit of their current release (checkout v4.4.0, setup-python v5.6.0, setup-node v4.4.0, gitleaks v2.3.9; no behaviour change); default token permissions none, each job read-only; checkouts keep no git credentials; 30-minute job limits; no `pull_request_target`, no secrets beyond the built-in token; weekly grouped Dependabot PRs for the actions; a test enforces all of this; PR template checklist updated |
| 15 | **Phase 1 manual test guide**: step-by-step script for the product owner to test every Phase 1 screen end to end in the browser (India and US), with expected results | 19, 35 | HIMS-OPS-016 | ✅ Done: [docs/testing/flow-part1.md](../testing/flow-part1.md): 21 parts, step by step in simple English (start HIMS, 3 browser windows, two-factor on the phone, every screen, the admin console, emails in the launcher window, safety checks that must be refused, US differences, troubleshooting, results sheet) |

After this queue, the next big step is **Phase 2 (Patient/MPI)**. It needs a P0 design signed off by
**PO + CLIN** (spec 26). I can draft that design for your approval.

---

## Verification checkpoint: after PR #8 (2026-10-27)

Everything marked ✅ below was re-verified before starting item 5.

| Check | Result |
|---|---|
| Git: local `development` = GitHub `development`, PR #1–#8 merged, working tree clean | ✅ |
| India (`HIMS`) and US (`HIMS_US`) databases: all migrations applied, audit append-only trigger present, 6 system roles, 14 permissions, catalogs (106 designations, 52 specialties, 57 qualification types) | ✅ both |
| Backend: 139 tests, lint/format, Django checks, migrations committed, OpenAPI contract in sync, dependency audit, production `check --deploy` | ✅ |
| Frontend: API types in sync, typecheck, lint, 14 tests, build, dependency audit | ✅ |
| End-to-end regression over HTTP (fresh database, two-factor enforced): 32 checks covering health, problem errors, MFA enforcement/setup/two-step sign-in, facilities + idempotent replay + stale-edit protection, departments, catalogs, staff onboarding + designation, invitation + single-use activation, no-access reference, permission-denied reference, password reset (no enumeration) + sessions ended, role grant, termination ends sessions and blocks sign-in, admin console with code, admin cannot read audit, admin theme, auditor two-factor, auditor finds references, all feature audit events present | ✅ 32/32 |
| Launcher: page, 10 themes, India/US/Europe cards | ✅ |
| Docs: no broken links, 18 ADRs = 18 index rows | ✅ (qualification count corrected 66 → 57; backlog rows added for HIMS-UI-001 and HIMS-OPS-012) |
| Not yet done (by design): `qa`/`staging`/`production` are 8 PRs behind `development` (no promotion yet); hosted environments (Render/Vercel) not created | ℹ️ |

## PR history (traceability, spec 25.3)

| PR | Ticket(s) | What |
|---|---|---|
| #1 | HIMS-OPS-002 | Manual CI runs; GitHub setup recorded |
| #2 | HIMS-OPS-002 (titled "HIMS-OPS-003" by mistake; HIMS-OPS-003 remains *Terraform modules*) | Environment branches renamed to `development`/`production` |
| #3 | HIMS-IAM-003 | Staff invitation and account activation |
| #4 | HIMS-IAM-004, HIMS-STAFF-009 | Password reset; hospital roles catalog; RBAC document |
| #5 | HIMS-UI-002 (extends HIMS-UI-001) | No-access page with audited reference; 10 themes; compact design |
| #6 | HIMS-IAM-006 | End all sessions on suspension/termination/password change |
| #7 | HIMS-OPS-012 | Runbook: updating every hospital database |
| #8 | HIMS-IAM-005 | Two-factor sign-in (MFA); secret-scan exceptions for reviewed false positives |
| #9 | HIMS-OPS-013 | Verification checkpoint after PR #8; PR history; doc corrections |
| #10 | HIMS-FAC-004 | Hospital locations: building → floor → ward → room → bed; bed status rules; bed manager role; Locations page |
| #11 | HIMS-ORG-003, HIMS-PLAT-018 | Numbering schemes (MRN, visit, invoice, claim) with Numbering page; admin console coverage for items 1–5 |
| #12 | HIMS-FAC-005 | Set up locations in the app: add/edit/deactivate buildings, floors, wards, rooms and beds on the Locations page |
| #13 | HIMS-ORG-004 | Feature settings per hospital, country and facility; Features page; ADR-019 |
| #14 | HIMS-STAFF-007, HIMS-IAM-013 | Staff detail/onboarding screens; roles and access screens; no self-granted access |
| #15 | HIMS-FAC-006 | Departments screen, facility edit screen, "close in order" rules |
| #16 | HIMS-AUD-003 | Audit log screen for auditors with search, details and CSV download |
| #17 | HIMS-IAM-015, HIMS-ORG-005 | Accounts screen (incl. people who are not staff), last-administrator protection, Hospital settings screen |
| #18 | HIMS-STAFF-005, HIMS-STAFF-006 | Licence/qualification documents, daily expiry alerts, Licence expiry page, ADR-020 |
| #19 | HIMS-FAC-007, HIMS-STAFF-010 | Department page (head, services, opening hours); Job titles & catalogs page |
| #20 | HIMS-IAM-016, HIMS-IAM-012 | "My sign-ins" on the Security page; Access reviews page; last administrator's role protected |
| #21 | HIMS-OPS-016 | Phase 1 manual test guide (`docs/testing/flow-part1.md`) |
| #22 | HIMS-SEC-010 | Audit tamper evidence: sealed hash chain, integrity checks, Audit integrity page, alerts |
| #23 | HIMS-IAM-017 | Cover arrangements (delegated access): Cover page, Security page section, admin console |
| #24 | HIMS-PLAT-012, HIMS-PLAT-015, HIMS-PLAT-016 | Hash-locked lockfiles, route-level code splitting, OpenTelemetry tracing, PHI-safe access logs |
| #25 | HIMS-PLAT-013, HIMS-DATA-001 | GitHub Actions pinned and least-privilege; generated data dictionary and ERDs; Artifact A index |
| #26 (this item; number assigned by GitHub) | HIMS-QA-001 | Playwright browser tests with accessibility checks; two-factor backup-code and link fixes; contrast fixes |
| (before PRs) | HIMS-PLAT-*, HIMS-ORG-*, HIMS-FAC-001..003, HIMS-IAM-001/002/009, HIMS-STAFF-001..004, HIMS-AUD-*, HIMS-PLAT-017, HIMS-UI-001 | Phase 1 foundation, admin console, launcher, themes (direct commits before the PR workflow existed) |

## Section-by-section

### §1 Executive summary · §2 Principles · §3 Personas

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §1 Confirmed direction (stack, monolith, dedicated deployment, IN+US) | ✅ | Followed in code; IN and US deployments run locally | — | — |
| §2.2 Principles 1, 4, 5, 6, 8, 9, 11 | ✅ | State guards, transactions, audit, isolation, modular monolith, PostgreSQL authority, end-to-end security | — | — |
| §2.2 Principles 2, 3, 7, 10, 12 | ⬜ | — | Apply with patient, orders, country adapters, integrations | 🔒 CLIN for 12 |
| §3 Personas (16 roles) | 🟡 7 system roles | Organization admin, auditor, facility admin, HR/credentialing officer, HOD, basic staff, bed manager / ward clerk; all 16 personas documented with ladders in [RBAC doc](Hospital_Departments_and_Doctors_RBAC.MD) | Clinical roles' permissions | 🔒 CLIN (approve RBAC doc §8) |

### §4 Functional scope

| § | Domain | Status | Done | Left (🔓 = can do now) | Dependency |
|---|---|---|---|---|---|
| 4.1 | Hospital & branches | 🟡 94% | Organization (one per deployment), facilities, country/timezone/currency, admin, **locations: buildings, floors, wards/units, rooms, beds** (HIMS-FAC-004), **numbering schemes for MRN, encounters, invoices, claims** (HIMS-ORG-003), **feature flags by organization, country and facility** (HIMS-ORG-004) | 🔓 logo/templates | Tax rules: 🔒 LEGAL |
| 4.2 | Departments | 🟡 85% | Create/edit, facility scope; department catalog & people per department documented; 52 specialties; **Departments screen** (counts of staff and wards, add/edit/deactivate) with **close-in-order rules** (HIMS-FAC-006); **department page with head, services offered and weekly opening hours** (HIMS-FAC-007) | — | Pricing/slots/escalation: 🔒 CLIN |
| 4.3 | Staff & credentials | 🟡 97% | Staff, qualifications (57 IN/US types), credentials, verification, termination, **designation catalog (106 titles, seniority 1–10, IN/US)**; **licence and qualification documents** and **daily expiry alerts** with a Licence expiry page (HIMS-STAFF-005/006) | 🔓 shifts/leave/on-call; screens done: staff detail, onboarding, postings, qualification and licence verification (HIMS-STAFF-007); **job titles, specialties and qualification types maintained in the app** (HIMS-STAFF-010) | Clinical privileges: 🔒 CLIN |
| 4.4 | Identity & access | 🟡 99% (rest blocked) | Login, sessions, scoped RBAC, suspension, admin console, invitation & activation, password reset (no enumeration, 60 min single-use link, ends all sessions, security notice), **session management** (register of sign-ins per user, end all sessions on suspension/termination/deactivation, "sign out of all devices"), **two-factor sign-in (MFA)** for privileged roles, **roles and access screens** (who has access where, give/remove access, custom roles; HIMS-IAM-013); **Accounts screen** for everyone who can sign in incl. people who are not staff (HIMS-IAM-015); **My sign-ins** (see and sign out your own devices; HIMS-IAM-016); **periodic access reviews** with reminders and auditor evidence (HIMS-IAM-012); **delegated access / cover arrangements** (time-limited, reason, audit, auto-end; HIMS-IAM-017) | — | SSO: 🔒 PO; break-glass rules: 🔒 CLIN |
| 4.5 | Patient registration & MPI | ⬜ | — | Demographics, MRN, duplicate detection | 🔒 PO+CLIN P0 sign-off |
| 4.6 | Appointments & OPD | ⬜ | — | All | 🔒 P0 |
| 4.7 | Encounters & admissions | ⬜ | — | All | 🔒 P0, CLIN |
| 4.8 | EHR/EMR | ⬜ | — | All | 🔒 CLIN |
| 4.9 | Nursing | ⬜ | — | All | 🔒 CLIN |
| 4.10 | Beds & wards | 🟡 40% | Ward/room/bed inventory with types, gender/age restrictions, isolation-capable rooms; bed status (available, maintenance, blocked, out of service) with reason, audit and `bed.status.changed` event; occupancy counts per ward and facility; Locations page **with in-app setup** (add, edit, deactivate every level; add numbered beds; HIMS-FAC-005) | 🔓 bed board view; assignment, transfer, housekeeping turnaround | Assignment/transfer/discharge: 🔒 P0 ADT (Phase 3) |
| 4.11 | Diet & kitchen | ⬜ | — | All | 🔒 CLIN |
| 4.12 | Housekeeping/equipment/transport | ⬜ | — | 🔓 equipment register | Workflows: 🔒 PO |
| 4.13 | Pharmacy | ⬜ | — | All | 🔒 CLIN, VENDOR (drug database) |
| 4.14 | eMAR | ⬜ | — | All | 🔒 CLIN |
| 4.15 | Laboratory | ⬜ | — | All | 🔒 CLIN, VENDOR (LIS) |
| 4.16 | Radiology | ⬜ | — | All | 🔒 CLIN, VENDOR (PACS) |
| 4.17 | Surgery/ICU | ⬜ | — | All | 🔒 CLIN |
| 4.18 | Insurance | ⬜ | — | All | 🔒 PAYER |
| 4.19 | Billing/RCM | ⬜ | — | All | 🔒 PO+LEGAL (tax), PAYER |
| 4.20 | Procurement/inventory/accounting | ⬜ | — | All | 🔒 PO (finance rules) |
| 4.21 | Patient portal | ⬜ | — | All | 🔒 needs 4.5+ |
| 4.22 | Documents & consent | 🟡 20% | Document storage for staff documents (type and size checks, no public links, audited downloads, archive not delete, per-hospital folders; ADR-020) | S3-compatible storage for hosted environments (HIMS-OPS-015), malware scanning (HIMS-SEC-013), patient documents with their domains | S3: 🔒 AWS/hosting; consent forms: 🔒 LEGAL |
| 4.23 | Notifications | ⬜ | — | 🔓 notification service (console/email locally) | SMS/WhatsApp: 🔒 VENDOR (DLT) |
| 4.24 | Reporting | ⬜ | — | All | 🔒 needs domains |
| 4.25 | Audit & governance | 🟡 85% | Who/what/when, before/after, logins, denials, admin changes, audit search, **Audit log screen and CSV export** (HIMS-AUD-003), **tamper evidence** (sealed hash chain, daily/on-demand integrity check, alerts, Audit integrity screen; HIMS-SEC-010) | 🔓 background check for very large logs (HIMS-SEC-017, later) | Retention/legal hold: 🔒 LEGAL; chain head copy to S3 Object Lock (HIMS-SEC-016): 🔒 AWS |

### §5 Workflows · §6 Technical architecture · §7 Dedicated deployment · §8 Repository

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §5.1–5.3 Admission, medication, claim flows | ⬜ | — | All | 🔒 §4 domains |
| §6.1 Modular monolith | ✅ | One Django project with domain apps | — | — |
| §6.2 Stack table | 🟡 90% | React/TS, MUI, TanStack, RHF+zod, DRF, PostgreSQL, Celery, Redis (optional locally), OpenAPI, Docker, **OpenTelemetry tracing** (HIMS-PLAT-016) | 🔓 S3-compatible storage adapter | — |
| §6.3 Components (outbox, idempotency, audit, tenant context) | ✅ | All present and tested; admin console covers every model (enforced by a test) | Integration gateway | 🔒 PAYER/VENDOR |
| §7.1–7.4 Per-organization deployment and isolation | 🟡 40% | Deployment ID, isolated cookies/cache/queues, single-org database, provisioning command, IN+US running separately | Control plane, export/retirement | 🔒 AWS + PO (account isolation) |
| §7.6 Cross-hospital reporting | ⬜ | — | Governed analytics pipeline | 🔒 LEGAL |
| §8 Repository layout | ✅ | As specified | — | — |

### §9 Data modelling · §10 Concurrency

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §9.2 Organization/Identity/Platform tables | 🟡 | organizations, facilities, departments, users, roles, permissions, role_assignments, staff_*, audit_events, outbox_events, idempotency_records, **buildings, floors, wards, rooms, beds**, **numbering_schemes, numbering_counters, issued_numbers**, **feature_flags** | 🔓 documents | consents: 🔒 LEGAL |
| §9.2 Patient/Clinical/Inpatient/Medication/Lab/Diet/Insurance/Billing tables | ⬜ | — | All | 🔒 P0 per domain |
| §9.4 Doctor & qualification model | ✅ | StaffMember, department assignment, qualification, credential | — | — |
| §10.1 Bed allocation race | 🟡 | Beds exist with row-locked, versioned status changes (stale change → 409); `occupied`/`reserved` can only be set by the future admission workflow | Allocation with partial unique index on active bed assignment | 🔒 P0 ADT |
| §10.2 Duplicate request/claim/payment/Celery protections | 🟡 | Idempotency keys, version checks, deduplicated tasks — all tested; **business numbers (MRN/encounter/invoice/claim) can never be issued twice** (row lock + unique index, 6-thread test) | Domain-specific cases | 🔒 domains |

### §11 Insurance · §12 Interoperability · §13 Security

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §11 Stedi and India adapters, eligibility, claims | ⬜ | — | All | 🔒 PAYER |
| §12 FHIR / ABDM / HIPAA | ⬜ | — | All | 🔒 partners, LEGAL |
| §13.1 Authentication | 🟡 MFA ✅ | Session lifecycle, throttling, no account enumeration, admin lockout, secure activation/reset tokens (signed, single use, never stored, kept out of URLs sent to servers), account recovery, **MFA for privileged users** (TOTP, two-step sign-in in app and admin console, backup codes, replay protection, attempt limits); the hospital can require two-factor for everyone and turn off forgot-password emails on its Features page | 🔓 step-up re-authentication (HIMS-IAM-007), 🔓 passkeys (HIMS-IAM-014) | SSO: 🔒 PO |
| §13.2 Authorization | 🟡 | RBAC + facility/department scope, default deny, separate permissions, escalation guard, **prompt termination of access** (all sessions deleted the moment employment ends), **nobody can give themselves access** (also in the admin console), system roles locked, custom-role edits versioned and audited, **the last hospital administrator can never be switched off** (no lock-out), nobody switches their own account; **periodic permission review** (HIMS-IAM-012: keep/remove every person's access, nobody reviews their own, removal ends access at once, evidence kept); **the last administrator's role cannot be removed**; **time-limited delegated access** (cover arrangements: no self-granting, no escalation, auditor access never lent, ends with the original access or the account; HIMS-IAM-017) | — | Patient/encounter scope & break-glass: 🔒 CLIN |
| §13.3 Data protection | 🟡 | Secrets kept out of git, PHI-minimised logs, **application-level encryption with rotatable keys** (authenticator secrets; production refuses to start without keys); **document access controls** (no public URLs, permission-checked and audited downloads, sandboxed responses) | 🔓 encryption at rest for documents (with S3/KMS) | TLS/KMS/backups: 🔒 AWS |
| §13.4 Auditability | 🟡 | Append-only (database trigger), restricted access, privileged actions audited; every "no access" / "permission denied" screen shows a reference number equal to the audit event's request ID (searchable by auditors on the **Audit log** screen, also via /audit?request_id=…); searching and exporting are themselves audited; **tamper detection** (HIMS-SEC-010: every record sealed into a keyed hash chain, whole chain checked daily and on demand, auditors emailed on problems) | — | Retention: 🔒 LEGAL; independent chain-head copy (HIMS-SEC-016): 🔒 AWS |
| §13.5 Security test cases (10) | 🟡 3/10 | Out-of-scope access, terminated user **reusing an old session (now deleted on every device, tested via API, admin console and direct deactivation)**, Celery context isolation (queues) | 🔓 secret-in-logs test, 🔓 restore test (local) | 7 need domains (notes, stock, documents, exports) |

### §14 Redis/Celery · §15 React · §16 REST API

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §14.2 Transactional outbox | ✅ | Dispatcher, retries, dead-lettering, consumer deduplication, inline mode for local development; first real consumers (invitation emails); daily scheduled jobs (session clean-up, **licence expiry alerts**, safe to re-run) | — | — |
| §14.3 Reliability rules | 🟡 | Late acknowledgement, idempotent tasks, durable state | Queue monitoring | 🔒 AWS (alarms); local Redis optional |
| §15.1 Role workspaces | 🟡 1/7 | Hospital-admin workspace (facilities with edit, departments, locations and beds with full in-app setup, numbering, features, staff with full detail and onboarding, roles and access, accounts, hospital settings); **auditor workspace** (Audit log) | 🔓 more admin screens | Clinical workspaces: 🔒 domains |
| §15.2 Frontend decisions | 🟡 | TypeScript, typed contracts, TanStack, RHF, backend authorization, **theme selector (10 white-based themes, WCAG AA contrast tested)**, compact modern design system (13px base, small sentence-case buttons, dense inputs/tables), permission-aware navigation and home page | 🔓 accessibility checks, 🔓 code splitting | — |
| §15.3 Patient chart | ⬜ | — | All | 🔒 4.5+ |
| §16 Endpoint table (18) | 🟡 4/18 | Hospital setup (provisioning), departments, staff, audit events; plus locations and beds (`/buildings`, `/floors`, `/wards`, `/rooms`, `/beds`, `/beds/{id}/status`, `/beds/bulk`, `/facilities/{id}/locations`) and numbering (`/numbering-schemes`, `/numbering-schemes/preview`, `/numbering-schemes/{id}/next-number`, `/issued-numbers`) and features (`/features`, `/features/{key}/change`, `/features/effective`); staff postings end, qualification verify, role edit; staff documents (`/staff/{id}/documents`, `/staff-documents/{id}/download`, `/archive`) and `/staff-credentials/expiring` | 14 domain endpoints | 🔒 domains |
| §16 Write-endpoint rules (8 items) | ✅ | Applied to all built endpoints | — | — |

### §17 AWS · §18 Non-functional · §19 Testing · §20 Roadmap · §21 Vertical slice

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §17 AWS deployment | ⬜ | Dockerfile ready | All | 🔒 AWS (deferred by choice) |
| §18 Non-functional requirements | 🟡 40% | **Accessibility**: WCAG 2.1 AA checks on every screen in the browser tests, contrast tested for all 10 themes, keyboard-only navigation tested; Consistency, request IDs, structured logs, **traces** linked to request IDs and log lines (off by default; HIMS-PLAT-016), first page download halved by code splitting (HIMS-PLAT-015), PHI-safe access logs | 🔓 SLO measurement | Traces/metrics/alarms in AWS (HIMS-PLAT-019, HIMS-OPS-004): 🔒 AWS |
| §19.1 Backend tests | 🟡 | 371 tests (incl. browser-test database reset refuses any real database; and data dictionary and ERDs match the models, every app in a domain, every table has a lifecycle rule, overrides point at real columns, credentials Secret and personal data Restricted, readable constraint text; CI workflow pinned to SHAs with release names, read-only tokens, no `pull_request_target` or extra secrets, checkouts without credentials, job time limits; and lockfiles match their `.in` files, every locked package has a checksum, tools use production versions; tracing off by default, API spans without search words and with the reference number, health checks untraced, outbound URLs without query strings, log lines carry trace ids, sampling, console exporter, access log without query strings; and cover arrangements: copies of the chosen roles for the period, start later, choose some roles, same person / self / too long / past start / overlap / switched-off refused, auditor and lent access never lent, no access-management permission → 403, end early with version and reason, original removed ends the copy, switching off either account ends it, lent admin access never counts as an administrator, finished cover does not block a new one, lists/filters/my cover, access review label, admin console arrange/refuse/end; and audit tamper evidence: chain sealed once and linked, batches, untouched log passes, changed/deleted record, link rebuilt without key, chain cut short, back-dated record never sealed, key rotation and unknown key, chain tables append-only, auditors emailed, API and admin console for auditors only, commands, production refuses to start without keys; and My sign-ins: own devices only, device names, sign out one / all others, this device kept, expired hidden; access reviews: snapshot, one at a time, keep/remove, removal ends access, reason required, no self-review, complete/cancel rules and versions, auditor read/download only, CSV, reminders once, admin console, last administrator's role protected; and department head rules and automatic clean-up, weekly hours validation and audit, services, catalog add/edit/switch-off and permissions, admin console checks; and documents: safe storage, type/size checks, ownership, audited sandboxed download, archive, admin console; expiry alerts: stages, once per stage, catch-up, renewal, skipped staff, command, list; deploy check; and accounts: list/kinds/roles, add account + invitation, switch off/on ends sessions, own/staff accounts refused, last administrator protected in API, admin console and staff termination, permissions; and audit screen: every event has a label, names, reference/person/area/day filters, bad filters → 400, only auditors, searches and exports audited, CSV formula-safe, admin console in words; and close-in-order rules for departments and facilities incl. admin console, counts and filters; and staff and access screens: detail names/account/expiry, end posting, verify qualification incl. no self-verification, custom role edit with version, system roles locked, no escalation, no self-granted access; and feature settings: defaults, hospital/facility/country rules, planned features locked, reason + version + audit, the 3 live features enforced, permissions, admin console): constraints, permissions, isolation, concurrency, outbox, admin (incl. every console page opens and every model is in the console), migrations, locations and bed status rules, numbering (formats, periods, no duplicates under 6 parallel threads, no gaps on rollback, GST length) | 🔓 secret-leak and restore tests | Insurance contract tests: 🔒 PAYER |
| §19.2 Frontend tests | 🟡 | 109 unit tests + **23 Playwright browser tests with axe accessibility checks** (HIMS-QA-001) (incl. contrast of menu and status colours on every theme, newer link in the same tab; every on-demand screen loads, "HIMS was updated" reload page, crash page without technical details; and Cover page: list, view-only, arrange with chosen roles and auditor role locked, skipped roles shown, end early with version, Security page section; and Audit integrity page: latest result, fingerprint, history, Check now, incident warning, problem details; and My sign-ins list and sign-out buttons; Access reviews list, start, keep, remove with reason, complete with version, auditor view; and department page: head, hours, services; catalogs page; and document links, upload with FormData, 10 MB check, Licence expiry page, Staff banner; and Accounts page, account actions, Hospital settings; and Audit log page: search only on request, reference links, area/event filters + CSV link, before/after; and Departments page, facility edit; and staff list/detail, end posting, verify, give/remove access, roles page; and Features page, forgot-password link hidden when off, Locations "turned off" message): client, themes, link tokens, home/no-access page, two-factor setup/sign-in/redirect, Locations page and bed status dialog, location setup (view-only hides buttons, add building with field error, edit ward with version + deactivation warning, add numbered beds with clash check, bed details), Numbering page (list, view-only, live preview + save, continue numbering) | — | — |
| §19.3 Clinical validation | ⬜ | — | All | 🔒 CLIN |
| §20 Phase 1 | 🟡 App ~98%; infra ~10% | Application part per tracker; exit criterion ("hospital configured, staff onboarded, isolation demonstrably enforced") met locally; CI checks and environment branches exist | Queue items 10, 11b, 12–14; **infrastructure automation (Terraform), hosted environments, deployment pipelines, observability/alarms** | Infra: 🔒 AWS/hosting decision (PO) |
| §20 Phases 2–6 | ⬜ | — | All | 🔒 P0/CLIN/PAYER/VENDOR |
| §21 Vertical slice (14 steps) | 🟡 4/14 | Steps 1–4 (hospital, departments, doctor onboarding, scoped access) | Steps 5–14 | 🔒 domains |

### §22 ADRs · §23 Readiness checklist · §24 Links

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §22 ADR-001…008 | ✅ | Recorded in docs/decisions | — | — |
| New ADR-009…020 | 🟡 Proposed | Written and implemented | Approval | 🔒 PO / Security |
| §23 Checklist (45 items) | 🟡 2 done, 6 partial | Migrations version-controlled, outbox tested | 37 items | 🔒 CLIN/LEGAL/AWS/PAYER |
| §24 Reference links | n/a | — | — | — |

### §25–27 Delivery standard, P0, P1

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §25 Requirement IDs & traceability | 🟡 | Ticket IDs in backlog and code | 🔓 formal HIMS-FR records for built features | — |
| P0-A Functional specs | 🟡 | Foundation domains | Clinical domains | 🔒 CLIN |
| P0-B Database design | 🟡 | Built domains (constraints, migrations); [locations and beds design](../architecture/data-architecture/locations-and-beds.md), [numbering design](../architecture/data-architecture/numbering-schemes.md), [facilities and departments](../architecture/data-architecture/facilities-and-departments.md) | 🔓 data dictionary | — |
| P0-C State machines | 🟡 | Employment status, credential verification, **bed status** (operational part; ADT part designed), **facility/department open-close rules** | Clinical state machines | 🔒 CLIN |
| P0-D Permission matrix | 🟡 | Administrative permissions (25, incl. `accounts.manage`, `catalogs.manage`, `access.reviews.view`, `access.reviews.manage`) + 7 system roles (bed manager added; numbering and feature settings for facility administrators); full clinical matrix **drafted** in [RBAC doc §8](Hospital_Departments_and_Doctors_RBAC.MD) | Approval | 🔒 CLIN |
| P0-E Provisioning/isolation | 🟡 | Application side, IN+US locally | Infrastructure side | 🔒 AWS |
| P0-F Integration contracts | ⬜ | — | All | 🔒 PAYER/VENDOR |
| P0-G Regulatory assessment | ⬜ | — | All | 🔒 LEGAL |
| P0-H Terminology | ⬜ | Starter catalogs | Code systems, licences | 🔒 CLIN, VENDOR |
| P0-I API & migration discipline | ✅ | OpenAPI and migration checks in CI | — | — |
| §27 P1 production readiness | ⬜ 5% | Structured logs | DR, runbooks, load tests, UAT | 🔒 AWS, CLIN |

### §28–30 Artifacts A, B, C

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §28 Artifact A — data architecture | 🟡 70% | §28.1 deliverables 1–12 for the built Phase 1 domains: **generated** data dictionary and ERDs (kept in step with the code by CI), [Artifact A index](../architecture/data-architecture/README.md) (ownership, classification and access matrix, lifecycle/correction, index ↔ query patterns, transactions and concurrency, history model, migrations/backfills, catalogs, data flows, synthetic data); domain designs for locations and beds, numbering, facilities and departments, access reviews, cover arrangements, audit integrity; §28.2 standards followed | 🔓 index check at production-like volume (HIMS-DATA-002) | P0 domains (patients first): 🔒 PO+CLIN (HIMS-DATA-003); retention periods: 🔒 LEGAL |
| §29 Artifact B — API contracts | 🟡 60% | Baseline, problem errors, idempotency, event envelope, OpenAPI check in CI | 🔓 per-endpoint contract docs; webhooks/adapters | 🔒 PAYER |
| §30 Artifact C — AWS/operations | ⬜ 5% | Dockerfile, infrastructure layout | Terraform, network, KMS, backups | 🔒 AWS |

### §31–36 Environments, GitHub, CI/CD, cost, DoD, decisions

| Item | Status | Done | Left | Dependency |
|---|---|---|---|---|
| §31 Environments | 🟡 | Local (IN+US + launcher), startup guard, config rules; feature settings documented as a schema (ADR-019, spec 31.4); environment branches `development`/`qa`/`staging`/`production` created (ADR-017) | Hosted Dev/QA/Staging/Prod on Render + Vercel | 🔒 PO (Render/Vercel accounts) |
| §32 GitHub workflow | 🟡 | Repo `vijayant-pandey/HIMS_Advanced` with branches development→qa→staging→production, ruleset `environment-branches` (PR required, 4 required checks, no force push/deletion), templates, CODEOWNERS template | GitHub Projects board | — |
| §33 CI/CD | 🟡 | PR CI runs on PRs into all four environment branches; **hash-checked installs** (`--require-hashes`), pip-audit on runtime and tool lockfiles, frontend bundle budget (HIMS-PLAT-012/015); **actions pinned to commit SHAs, read-only tokens, no persisted credentials, job time limits, Dependabot for actions** (HIMS-PLAT-013); data dictionary freshness check (HIMS-DATA-001) | Run on GitHub; Render/Vercel auto-deploy per branch | 🔒 GH, PO |
| §34 Cost strategy | 🟡 | Stage A (local, no spend) | Stages B–D | 🔒 AWS |
| §35 Definition of Done | 🟡 | Tests, migrations, contracts, no secrets | Environment/QA evidence | 🔒 AWS |
| §36 Open decisions (19) | ⬜ 0/19 | ADRs propose answers | Decisions | 🔒 PO, LEGAL, CLIN, Finance |

---

## Change log

| Date | Item | Sections affected |
|---|---|---|
| 2026-10-25 | Phase 1 foundation, admin console, IN+US local deployments, launcher | 4.1–4.4, 4.25, 6–10, 13–16, 19, 21, 28–33 |
| 2026-10-26 | UI theme selector (HIMS-UI-001) across launcher, apps and admin | 15.2 |
| 2026-10-26 | Environment branches qa/staging, CI on all four, ADR-017 (Render + Vercel interim hosting) | 31, 32, 33 |
| 2026-10-26 | Code pushed to GitHub, branch ruleset, manual CI trigger (HIMS-OPS-002) | 32, 33 |
| 2026-10-26 | Environment branches renamed to development/production; CI, README, ADR-017 updated | 31, 32, 33 |
| 2026-10-26 | Staff invitation & account activation (HIMS-IAM-003): email link, activation page, resend from API/admin, outbox inline mode locally | 4.4, 13.1, 14.2, 19 |
| 2026-10-26 | Password reset (HIMS-IAM-004); hospital roles catalog + RBAC document (HIMS-STAFF-009); HIMS-UI-002 tracked | 3, 4.2, 4.3, 4.4, 13.1, 26.4 |
| 2026-10-26 | HIMS-UI-002: no-access welcome page (audited reference), friendlier 403, 10 themes, compact modern design | 13.4, 15.2 |
| 2026-10-26 | HIMS-IAM-006: end all sessions on suspension/termination/deactivation, password change and admin sign-out; session register; nightly expired-session cleanup | 4.4, 13.2, 13.5, 14 |
| 2026-10-26 | Runbook: updating every hospital database after a merge (docs/workflows/database-migrations.md) | 26.9, 28.7, 31 |
| 2026-10-26 | HIMS-IAM-005: two-factor sign-in (MFA) for privileged roles, Security page, admin-console code step, encrypted secrets, ADR-018 | 4.4, 13.1, 13.3, 13.4 |
| 2026-10-27 | Verification checkpoint after PR #8 (all gates + 32-step end-to-end regression); docs corrected (qualification count, backlog rows, PR history) | 25.3 |
| 2026-10-27 | HIMS-FAC-004: locations (building → floor → ward → room → bed), bed status rules, bed manager role, Locations page, design doc; HIMS-FAC-005 (in-app setup screens) added to the queue | 3, 4.1, 4.10, 9.2, 10.1, 15.1, 16, 19, 26 (P0-B/C/D), 28 |
| 2026-10-27 | HIMS-ORG-003: numbering schemes (MRN, encounter, invoice, claim) with Numbering page, preview, continue-from-previous-system, issued register, India/US defaults, design doc. HIMS-PLAT-018: admin console covers every model (test-enforced), password-reset action, full bed status and location drill-down in the console | 4.1, 6.3, 9.2, 10.2, 15.1, 16, 19, 26 (P0-B/D), 28 |
| 2026-10-28 | HIMS-FAC-005: set up locations in the app (add/edit/deactivate buildings, floors, wards, rooms; add numbered beds; bed details); location tree now carries versions and department names; admin console re-checked for items 1–6 | 4.10, 15.1, 19 |
| 2026-10-28 | HIMS-ORG-004: feature settings by organization, country and facility (Features page, 3 live features, 12 planned modules, admin console, ADR-019); admin console re-checked for items 1–7 | 4.1, 7.2, 13.1, 15.1, 16, 19, 22, 26 (P0-D), 31.4 |
| 2026-10-28 | HIMS-STAFF-007 + HIMS-IAM-013: staff detail/onboarding screens, roles and access screens, end postings, verify qualifications, edit custom roles, nobody can give themselves access; gaps recorded as queue items 8b–8e (departments, audit log, hospital settings, accounts without a staff record) | 3, 4.3, 4.4, 13.2, 15.1, 16, 19 |
| 2026-10-28 | HIMS-FAC-006: Departments screen, facility edit screen, close-in-order rules (app, API and admin console), staff list by department, design doc; gap recorded as queue item 8f (department head, services, hours) | 4.1, 4.2, 15.1, 19, 26 (P0-B/C), 28 |
| 2026-10-28 | HIMS-AUD-003: Audit log screen for auditors (search, plain-language events, before/after, reference links), CSV export (audited, formula-safe), clear 400s for bad filters, admin console audit list in words | 4.25, 13.4, 15.1, 19 |
| 2026-10-28 | HIMS-IAM-015 + HIMS-ORG-005: Accounts screen (incl. people who are not staff, add account, switch off/on, reset two-factor, sign out), last-administrator protection everywhere, Hospital settings screen; item 9 set as next | 4.1, 4.4, 13.2, 15.1, 19, 26 (P0-D) |
| 2026-10-29 | HIMS-STAFF-005/006: licence and qualification documents (ADR-020), daily expiry alerts, Licence expiry page; queue item 15 added (Phase 1 manual test guide for the PO); HIMS-OPS-015 (S3 document storage) recorded | 4.3, 4.22, 13.3, 14, 16, 19, 22 |
| 2026-10-30 | Status check after PR #18: both local databases fully migrated (India and US: 22 permissions, 7 system roles, 4 numbering schemes, 15 feature settings); gaps recorded as 8g (catalog screens) and 8h ("My sign-ins") | 4.2, 4.3, 4.4, 13.5 |
| 2026-10-30 | Phase 1 shown in two parts per spec 20: application ~96%, infrastructure/hosting ~10% (previously only the application part was counted) | 20 |
| 2026-10-30 | HIMS-FAC-007 + HIMS-STAFF-010: department page (head, services, weekly opening hours) and Job titles & catalogs page; 8h + item 11 next | 4.2, 4.3, 19, 26 (P0-D) |
| 2026-10-30 | HIMS-IAM-016 + HIMS-IAM-012: "My sign-ins" on the Security page and periodic access reviews (page, reminders, CSV evidence, admin console); last administrator's role protected from removal; gap recorded as 11b (delegated access, HIMS-IAM-017); item 15 next | 4.4, 13.2, 13.5, 19, 26 (P0-D) |
| 2026-10-30 | HIMS-OPS-016: Phase 1 manual test guide (`docs/testing/flow-part1.md`) for the product owner | 19, 35 |
| 2026-10-30 | HIMS-SEC-010: audit tamper evidence (sealed keyed hash chain, daily and on-demand integrity check, auditor alerts, Audit integrity page, admin console, `seal_audit_log` / `check_audit_log` commands, new required secret `HIMS_AUDIT_CHAIN_KEYS` for hosted environments); ADR-013 updated; gaps HIMS-SEC-016 (🔒 AWS) and HIMS-SEC-017 recorded; item 11b next | 4.25, 13.4, 19 |
| 2026-10-30 | HIMS-IAM-017: cover arrangements / delegated access (Cover page, Security page section, "Cover for …" on the Access page, access-review label, admin console, emails, auto-end on account switch-off or original removal, `HIMS_DELEGATION_MAX_DAYS`); gaps HIMS-IAM-018 (clinical delegation, 🔒 CLIN) and HIMS-IAM-019 (self-service requests) recorded; item 14 next | 4.4, 13.2, 19 |
| 2026-10-30 | HIMS-PLAT-012/015/016 (item 14): hash-locked lockfiles, route-level code splitting with bundle budget, OpenTelemetry tracing (off by default, PHI-safe), PHI-safe gunicorn access logs, exact Node/Python versions; ADR-021, ADR-014 updated; how-tos for tracing and dependencies; gaps HIMS-PLAT-019 (🔒 AWS) and 14b (HIMS-PLAT-013) recorded; item 14b next | 6.2, 18, 19, 31.3, 33 |
| 2026-10-30 | HIMS-PLAT-013 (item 14b): GitHub Actions pinned to commit SHAs, least-privilege tokens, no persisted credentials, job limits, Dependabot for actions, enforced by a test. HIMS-DATA-001 (item 12): generated data dictionary and ERDs with CI freshness check; Artifact A index for spec 28.1; gaps HIMS-DATA-002/003 recorded; item 13 next | 28, 33 |
| 2026-10-30 | HIMS-QA-001 (item 13): Playwright browser tests + axe accessibility checks, `browser-tests` workflow; fixed backup codes not shown, same-tab link, contrast, loading-bar names; test guide 8.1/9.1 corrected (invitation is sent automatically). Phase 1 dependency-free queue finished | 18, 19 |
