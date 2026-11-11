# Requirement records: sign-in, accounts and access

Spec sections 4.4, 13.1, 13.2, 13.5. Format: [README](README.md). Endpoints:
[sign-in and accounts](../architecture/api-and-integrations/endpoints/identity.md),
[roles, reviews and cover](../architecture/api-and-integrations/endpoints/access_control.md).

### HIMS-IAM-001

| Field | Record |
|---|---|
| ID and title | HIMS-IAM-001 Own user model (random ID, email in any case), Argon2 passwords, password policy |
| Business/clinical reason | Accounts must be unique per email and passwords stored safely (spec 13.1). Owner: PO |
| Actors | Every person who signs in; the invitation and reset flows set passwords |
| Preconditions | None |
| Main success path | Accounts are found by email regardless of case; passwords are hashed with Argon2 and checked against the policy |
| Alternate/failure paths | Weak, common or name-like password → 400 with the rule broken; a second account with the same email in another case is refused |
| Data effects | `users` |
| Security classification | Credentials (restricted): hashes only, never shown |
| Audit requirement | `user.created` |
| Idempotency/concurrency | Unique index on lower-case email |
| Integration dependencies | None |
| Acceptance criteria | `Mary@x` and `mary@x` are one account; no plain password is ever stored or logged |
| Test evidence | `apps/identity/tests/test_auth.py`, `common/tests/test_secrets_never_logged.py` |
| Release risk | Privacy if weakened. Rollback: none needed (hash upgrades on sign-in) |

### HIMS-IAM-002

| Field | Record |
|---|---|
| ID and title | HIMS-IAM-002 Session sign-in, sign-out and "who am I"; CSRF; rate limits; answers that do not reveal accounts; audit |
| Business/clinical reason | Safe sign-in for every user (spec 13.1). Owner: PO |
| Actors | Anyone (sign-in); signed-in users (sign-out, who am I) |
| Preconditions | Active account with a password |
| Main success path | Get a CSRF token, sign in, receive a session cookie; `me` returns permissions with scope |
| Alternate/failure paths | Wrong email or password → the same 400 `INVALID_CREDENTIALS`; more than 10 tries a minute from one address → 429; switched-off account → same answer as wrong password |
| Data effects | `user_sessions`, Django sessions |
| Security classification | Credentials (restricted) |
| Audit requirement | `auth.login`, `auth.login_failed`, `auth.logout` |
| Idempotency/concurrency | Each sign-in is a new session |
| Integration dependencies | None |
| Acceptance criteria | No answer differs between "no such account" and "wrong password"; the limit cannot be dodged by changing `X-Forwarded-For` (HIMS-SEC-014) |
| Test evidence | `apps/identity/tests/test_auth.py`, `common/tests/test_client_ip_and_headers.py`; browser test `01-sign-in.spec.ts`; manual test Part 1 |
| Release risk | Privacy and availability. Rollback: deploy the previous image |

### HIMS-IAM-003

| Field | Record |
|---|---|
| ID and title | HIMS-IAM-003 Invitation and account activation (follows `staff.member.created`) |
| Business/clinical reason | New staff choose their own password; administrators never know it. Owner: PO |
| Actors | Staff administrators (`staff.manage`) send; the invited person accepts (no sign-in) |
| Preconditions | Staff member with an email; or a non-staff account (HIMS-IAM-015) |
| Main success path | Adding staff sends an invitation by email (outbox); the person opens the link, chooses a password, signs in |
| Alternate/failure paths | Expired, used or replaced link → `INVITATION_INVALID` with the same answer for all; already active → `ALREADY_ACTIVATED`; switched-off account → refused |
| Data effects | `user_invitations` (hashed token), `users`; outbox `staff.member.created`; `notifications` |
| Security classification | Credentials (restricted): token hashed, single use |
| Audit requirement | `user.invitation.issued`, `user.invitation.accepted`, `user.invitation.rejected` |
| Idempotency/concurrency | A new invitation ends the previous one; acceptance is single use under a row lock |
| Integration dependencies | Email (console locally); the invitation follows the outbox event, and a failed email is retried by the scheduled job |
| Acceptance criteria | A link works once, for a limited time; the second browser can sign in after activation |
| Test evidence | `apps/identity/tests/test_invitations.py`; browser test `03-staff-and-access.spec.ts`; manual test Part 9 |
| Release risk | Privacy if links leaked (hashed, short-lived). Rollback: send a new invitation |

### HIMS-IAM-004

| Field | Record |
|---|---|
| ID and title | HIMS-IAM-004 Password reset (answers that do not reveal accounts; time-limited single-use links) |
| Business/clinical reason | People who forget their password regain access without an administrator. Owner: PO |
| Actors | Anyone (request, inspect, confirm) |
| Preconditions | Active account |
| Main success path | Request → always 202 with the same message; email with link; choose a new password; all old sessions end |
| Alternate/failure paths | Unknown email → same 202, nothing sent; expired or used link → `PASSWORD_RESET_INVALID`; more than 5 requests a minute → 429 |
| Data effects | `user_password_resets` (hashed token), `users`, `user_sessions` |
| Security classification | Credentials (restricted) |
| Audit requirement | `user.password_reset.requested`, `user.password_reset.completed`, `user.password_reset.rejected`, `auth.sessions.ended` |
| Idempotency/concurrency | A new request ends the previous link; single use under a row lock |
| Integration dependencies | Email |
| Acceptance criteria | Nobody can tell from the answer whether an email has an account; after a reset no old session works |
| Test evidence | `apps/identity/tests/test_password_reset.py`; manual test Part 15 |
| Release risk | Privacy. Rollback: previous image |

### HIMS-IAM-005

| Field | Record |
|---|---|
| ID and title | HIMS-IAM-005 Two-factor sign-in (authenticator app), required for privileged roles (ADR-018) |
| Business/clinical reason | Administrator accounts must not fall to a stolen password (spec 4.4, 13.1). Owner: PO |
| Actors | Every user (optional); privileged roles (required); `accounts.manage` to reset a lost phone |
| Preconditions | Signed in |
| Main success path | Set up with a QR code, confirm with a code, keep 10 backup codes; later sign-ins ask for a code |
| Alternate/failure paths | Wrong code → `MFA_CODE_INVALID`, five failures end the attempt; privileged user without it → 403 `MFA_SETUP_REQUIRED` everywhere until set up; lost phone → administrator reset (not for yourself) |
| Data effects | `user_mfa_devices` (encrypted secret), `user_mfa_recovery_codes` (hashed) |
| Security classification | Credentials (restricted) |
| Audit requirement | `auth.mfa.enabled`, `auth.mfa.verified`, `auth.mfa.failed`, `auth.mfa.recovery_code_used`, `auth.mfa.recovery_codes_regenerated`, `auth.mfa.disabled`, `auth.mfa.reset` |
| Idempotency/concurrency | One device per person; backup codes single use under a row lock |
| Integration dependencies | None (codes are computed on the server) |
| Acceptance criteria | A privileged user cannot reach any permission endpoint without two-factor in the session; the console asks for the code too |
| Test evidence | `apps/identity/tests/test_mfa.py`; browser test `01-sign-in.spec.ts`; manual test Part 1 |
| Release risk | Availability if a phone is lost (administrator reset). Rollback: previous image |

### HIMS-IAM-006

| Field | Record |
|---|---|
| ID and title | HIMS-IAM-006 End every session on suspension, termination and password change |
| Business/clinical reason | Someone who leaves or is suspended must lose access at once (spec 13.5). Owner: PO |
| Actors | Staff administrators, account administrators; the person (password change) |
| Preconditions | Open sessions |
| Main success path | Suspending, terminating, switching off an account or changing a password deletes all its sessions; "Sign out of all devices" does it on request |
| Alternate/failure paths | Nothing to end → still audited with count 0 |
| Data effects | `user_sessions`, Django sessions |
| Security classification | Credentials (restricted) |
| Audit requirement | `auth.sessions.ended` with count and reason |
| Idempotency/concurrency | Repeating is harmless |
| Integration dependencies | None |
| Acceptance criteria | The next request of a terminated person is 401 |
| Test evidence | `apps/identity/tests/test_sessions.py`, `apps/staff/tests/test_staff_onboarding.py`; manual test Part 19 |
| Release risk | Privacy if broken. Rollback: previous image |

### HIMS-IAM-007

| Field | Record |
|---|---|
| ID and title | HIMS-IAM-007 "Confirm it's you" before sensitive actions |
| Business/clinical reason | An unattended signed-in screen must not let someone grant access or download evidence. Owner: PO |
| Actors | Anyone performing an action listed as sensitive (23 endpoints) |
| Preconditions | Signed in |
| Main success path | The action answers 403 `REAUTH_REQUIRED`; the person enters their password (and code, or a passkey); the action is allowed for 15 minutes (`HIMS_CONFIRM_IDENTITY_MINUTES`) |
| Alternate/failure paths | Wrong password → `REAUTH_FAILED`; five failures → signed out (`REAUTH_LOCKED`); more than 10 tries a minute → 429 |
| Data effects | Session only |
| Security classification | Credentials (restricted) |
| Audit requirement | `auth.identity_confirmed`, `auth.identity_confirm_failed`, `auth.identity_confirm_locked` |
| Idempotency/concurrency | One window per session |
| Integration dependencies | None |
| Acceptance criteria | Granting a role, exporting the audit log and similar actions are refused without a recent confirmation; the console has the same rule |
| Test evidence | `apps/identity/tests/test_confirm_identity.py`; manual tests Parts 17 and 18f |
| Release risk | Usability only. Rollback: Features setting turns it off per hospital |

### HIMS-IAM-009

| Field | Record |
|---|---|
| ID and title | HIMS-IAM-009 Scoped roles: permission catalog, roles, facility/department grants, default deny, no escalation |
| Business/clinical reason | Least privilege (spec 13.2): people get only what their job needs, only where they work. Owner: PO; role catalog approved for now by CLIN/LEGAL/PO 2026-11-08 |
| Actors | `access.roles.view`, `access.roles.manage`, `access.assignments.manage` |
| Preconditions | Organization; system roles created at provisioning |
| Main success path | Grant a role to a person for the whole hospital, a facility or a department, optionally until a date |
| Alternate/failure paths | Granting more than you hold at that scope → 403; granting to yourself → refused; system roles cannot be edited; anything not declared on an endpoint is denied |
| Data effects | `permissions`, `roles`, `role_permissions`, `role_assignments` |
| Security classification | Access control (restricted) |
| Audit requirement | `access.role.created`, `access.role.updated`, `access.role.assigned`, `access.role.revoked`, `access.denied` |
| Idempotency/concurrency | Idempotency-Key on grants; `version` on roles; "confirm it's you" on grants |
| Integration dependencies | None |
| Acceptance criteria | Every endpoint declares its permission (test); a facility grant never opens another facility (tests both ways) |
| Test evidence | `apps/access_control/tests/test_authorization.py`, `common/contracts/tests/test_contracts.py`; manual test Part 11 |
| Release risk | Privacy if a grant leaks scope. Rollback: revoke the assignment |

### HIMS-IAM-012

| Field | Record |
|---|---|
| ID and title | HIMS-IAM-012 Periodic access reviews |
| Business/clinical reason | Regulators expect regular review of who can see what (HIPAA, DPDP). Owner: PO, compliance |
| Actors | `access.reviews.manage` (run), `access.reviews.view` (auditors read and download) |
| Preconditions | Role assignments exist |
| Main success path | Start a review (snapshot of all access); decide keep or remove for each person; complete; download the CSV |
| Alternate/failure paths | Nobody decides on their own access; completing with undecided items is refused; removing ends the access at once |
| Data effects | `access_reviews`, `access_review_items`, `access_review_reminders`, `role_assignments` |
| Security classification | Access control (restricted) |
| Audit requirement | `access.review.started`, `access.review.decided`, `access.review.completed`, `access.review.cancelled`, `access.review.exported`, `access.review.reminder_sent` |
| Idempotency/concurrency | `version` on the review; decisions under row locks |
| Integration dependencies | Email reminders |
| Acceptance criteria | Removed access is gone the moment it is decided; the CSV needs "confirm it's you" |
| Test evidence | `apps/access_control/tests/test_access_reviews.py`; manual test Part 16 |
| Release risk | Privacy. Rollback: grant again (audited) |

### HIMS-IAM-013

| Field | Record |
|---|---|
| ID and title | HIMS-IAM-013 Roles and access screens |
| Business/clinical reason | Administrators manage access without a developer, and auditors can see what each permission opens. Owner: PO |
| Actors | `access.roles.view`, `access.roles.manage`, `access.assignments.manage` |
| Preconditions | HIMS-IAM-009 |
| Main success path | Access page: who has access, roles, and the API endpoints each permission opens (HIMS-DOC-001); grant from the person's Staff page |
| Alternate/failure paths | View-only users see no change buttons; no self-granting |
| Data effects | As HIMS-IAM-009 |
| Security classification | Access control (restricted) |
| Audit requirement | As HIMS-IAM-009 |
| Idempotency/concurrency | As HIMS-IAM-009 |
| Integration dependencies | None |
| Acceptance criteria | Only custom roles are editable, sending the version |
| Test evidence | Frontend `AccessPage.test.tsx`; browser test `03-staff-and-access.spec.ts`; manual test Part 11 |
| Release risk | Low |

### HIMS-IAM-014

| Field | Record |
|---|---|
| ID and title | HIMS-IAM-014 Passkeys as an additional second factor |
| Business/clinical reason | Phishing-resistant second factor (WebAuthn) for sign-in and "confirm it's you". Owner: PO |
| Actors | Anyone signed in (own passkeys); `accounts.manage` removes one in the console |
| Preconditions | Two-factor set up; a device that supports passkeys |
| Main success path | Add a passkey after "confirm it's you"; use it at sign-in or to confirm |
| Alternate/failure paths | Wrong origin, replayed challenge or unknown key → `PASSKEY_NOT_ACCEPTED`; expired challenge → `MFA_CHALLENGE_EXPIRED` |
| Data effects | `user_passkeys` (public keys only) |
| Security classification | Credentials (restricted) |
| Audit requirement | `auth.passkey.added`, `auth.passkey.removed`, `auth.mfa.verified` |
| Idempotency/concurrency | Sign counter checked under a row lock |
| Integration dependencies | The browser's WebAuthn; no outside service |
| Acceptance criteria | A passkey from another site or a replay is refused |
| Test evidence | `apps/identity/tests/test_passkeys.py`; manual test Part 18o |
| Release risk | Low (authenticator codes still work). Rollback: remove passkeys |

### HIMS-IAM-015

| Field | Record |
|---|---|
| ID and title | HIMS-IAM-015 Accounts screen, including people who are not staff; last administrator protected |
| Business/clinical reason | Auditors, consultants and IT need accounts without being staff; the hospital must never lose its last administrator. Owner: PO |
| Actors | `access.roles.view` (list), `accounts.manage` |
| Preconditions | Organization |
| Main success path | Add a non-staff account (invitation sent); switch off and on; reset two-factor; sign out everywhere |
| Alternate/failure paths | Staff accounts follow employment (`ACCOUNT_FOLLOWS_EMPLOYMENT`); last administrator → `LAST_ADMINISTRATOR`; own account → `SELF_ACCOUNT_CHANGE` |
| Data effects | `users`, `user_invitations`, `user_sessions` |
| Security classification | Personal data (confidential) |
| Audit requirement | `user.account.created`, `user.account.deactivated`, `user.account.reactivated`, `auth.mfa.reset`, `auth.sessions.ended` |
| Idempotency/concurrency | Idempotency-Key on create; row locks on changes |
| Integration dependencies | Email |
| Acceptance criteria | The last administrator can never be switched off or lose the role |
| Test evidence | `apps/identity/tests/test_accounts.py`; manual test Part 12 |
| Release risk | Availability if every administrator were lost (prevented). Rollback: reactivate |

### HIMS-IAM-016

| Field | Record |
|---|---|
| ID and title | HIMS-IAM-016 "My sign-ins": your open sessions; sign out other devices |
| Business/clinical reason | People can see and end sessions they do not recognize. Owner: PO |
| Actors | Anyone signed in (own sessions only) |
| Preconditions | Signed in |
| Main success path | Security page lists devices with address and last use; sign out one or all others |
| Alternate/failure paths | Another person's session → 404 |
| Data effects | `user_sessions` |
| Security classification | Personal data (confidential) |
| Audit requirement | `auth.sessions.ended` |
| Idempotency/concurrency | Repeating is harmless |
| Integration dependencies | None |
| Acceptance criteria | The ended device's next request is 401 |
| Test evidence | `apps/identity/tests/test_sessions.py`; manual test Part 15 |
| Release risk | Low |

### HIMS-IAM-017

| Field | Record |
|---|---|
| ID and title | HIMS-IAM-017 Cover: temporary, time-limited delegated access with reason and audit |
| Business/clinical reason | When someone is away, a colleague covers their administrative roles for a limited time (spec 4.4). Clinical delegation is Phase 2 (HIMS-IAM-018). Owner: PO |
| Actors | `access.roles.view` (list), `access.assignments.manage` (arrange and end); the covering person sees their cover on the Security page |
| Preconditions | The away person holds roles the arranger may grant |
| Main success path | Choose who covers whom, which roles, from and until, with a reason; the roles are lent and end by themselves |
| Alternate/failure paths | Lending more than you may grant → 403; overlapping or past dates → 400; ending early removes every lent role at once |
| Data effects | `access_delegations`, `role_assignments` |
| Security classification | Access control (restricted) |
| Audit requirement | `access.delegation.created`, `access.delegation.ended`, `access.role.assigned`, `access.role.revoked` |
| Idempotency/concurrency | Idempotency-Key on create; row lock on end |
| Integration dependencies | None |
| Acceptance criteria | Cover never outlives its end date (daily job); never more than the arranger may grant |
| Test evidence | `apps/access_control/tests/test_delegations.py`; manual test Parts 11 and 12 |
| Release risk | Privacy if cover outlived its date (job tested). Rollback: end the cover |
