# Confirm before sensitive actions (spec 13.1; HIMS-IAM-007)

Decision record: [ADR-023](../decisions/ADR-023-confirm-before-sensitive-actions.md).

## What it does

Spec 13.1 asks for "reauthentication for sensitive actions where justified". If someone walks up to
an unlocked computer, or steals a signed-in session, they still should not be able to change who
can do what. So HIMS asks for the person's **password, and their authenticator code if they use
one**, before a sensitive action.

- Once confirmed, the person is not asked again for **15 minutes** (`HIMS_CONFIRM_IDENTITY_MINUTES`,
  1 to 60 in managed environments).
- **Signing in counts**, so nobody is asked right after signing in.
- The confirmation belongs to that session only. It ends with the session and never carries over to
  another device.
- The person can end it early: **Security → Sensitive actions → End now**.
- A backup code works in place of the authenticator code.

## What asks

| Action | Where in the app | API action |
|---|---|---|
| Create or change a role | Access | `roles`: create, update |
| Give or remove a role | Access, Staff, Accounts | `role-assignments`: create, revoke |
| Arrange cover | Cover | `access-delegations`: create |
| Decide an access review item (it can remove access) | Access reviews | `access-reviews`: decide |
| Download an access review | Access reviews | `access-reviews`: export |
| Download the audit log | Audit log | `audit-events`: export |
| Make a backup (a full copy of every record and document; HIMS-OPS-009) | Backups | `backups`: create |
| Add an account; switch one off or on | Accounts | `accounts`: create, deactivate, reactivate |
| Reset someone's two-factor; sign them out everywhere | Accounts | `accounts`: reset-two-factor, sign-out-everywhere |
| Suspend or terminate staff (ends their access) | Staff | `staff`: update, only for those two statuses |
| Change a Feature setting | Features | `features`: change |

**In the admin console** the same areas ask before saving or running an action: users (including
setting a password), roles, role assignments, access reviews and their items, cover, staff,
feature settings, "Make a backup now", and **downloading an access review or audit events as CSV**
(added 2026-11-09, HIMS-SEC-015). Looking does not ask. Nothing is changed until the person has confirmed, and they
then repeat what they were doing.

**Why these:** each one changes who can do what, ends someone's access, weakens a security setting
or takes bulk personal data out of the system. Everyday work does not ask, because asking too often
teaches people to type their password without thinking.

**Already protected in another way:** turning off your own two-factor and new backup codes need a
code; changing a password needs the current one.

**Adding one:** add the action to the view's `sensitive_actions`, or call
`confirmation.require(request)` for a conditional one, and add it to this table and to
`test_every_sensitive_action_stays_declared`. Clinical actions come with their own design in Phase 2
(HIMS-IAM-020).

## How it works

1. The server refuses the request with `403` and code `REAUTH_REQUIRED`. Nothing has changed, and
   this is not recorded as an access denial, since the person is allowed to do it.
2. The app shows **Confirm it's you** over whatever screen is open. Screens need no code for this.
3. After the person confirms, the app sends the same request again, with the same idempotency key,
   so it finishes by itself. Cancelling shows the server's message on the screen.

Permission is checked first, so a person who may not do something is refused without being asked for
a password.

## Wrong tries

- Each wrong try is audited. The rate limit is `HIMS_THROTTLE_CONFIRM_IDENTITY` (default 10 a minute).
- **Five wrong tries end the session**, so whoever holds it must sign in again, which needs the
  password. The count clears after a right try.
- An authenticator or backup code is only used up if the password was right.

## Audit records

| Event | Meaning |
|---|---|
| `auth.identity_confirmed` | Confirmed; shows whether a backup code was used |
| `auth.identity_confirm_failed` | A wrong try, with its number |
| `auth.identity_confirm_locked` | Signed out after too many wrong tries |

The action itself is audited as always. An auditor seeing several failed tries then a sign-out for
one person should treat it as a possible stolen session.

## The hospital's control

**Features → Confirm before sensitive actions** turns it off or on for the whole hospital, with a
reason, and is audited. It is on by default and should stay on. Turning it off is itself a sensitive
action. The same setting is in the admin console.

No database change: the time is kept in the person's session.
