# Cover arrangements: delegated access (HIMS-IAM-017)

Spec 4.4 ("account suspension, termination, **delegated access** and periodic access reviews"),
13.2 (least privilege, separation of duties, prompt termination of access). All tables live in the
hospital's own database (one per deployment).

## 1. In plain words

When someone is away (leave, conference, training), an administrator can let a colleague
**cover** for them: for a limited time, the colleague works with some or all of the away
person's access. Everything the colleague does is still recorded under the colleague's own name.
The access ends by itself at the end date, or earlier if an administrator ends it.

Words used: the **covered person** (delegator) lends access; the **covering person** (delegate)
receives it.

## 2. How it is stored

| Table | Purpose | Key rules |
|---|---|---|
| `access_delegations` | One cover arrangement | Covered person, covering person (must be two different people), `starts_at`, `ends_at` (after the start), reason, who arranged it, `ended_at` / `ended_by` / `end_reason` when ended early, `version` for safe concurrent edits. Never deleted. |
| `role_assignments` (existing) | The lent access | Each lent role is an ordinary role assignment for the covering person, valid only from `starts_at` to `ends_at`, with two new links: `delegation` (which arrangement) and `delegated_from` (the covered person's original assignment). |

Because lent access is an ordinary role assignment, **the permission check is unchanged**:
scope (whole hospital / facility / department), start and end times, revocation, two-factor rules,
the Access page, access reviews and the audit log all work exactly as for any other access.

Status is worked out from the times: **Starts later** (before `starts_at`), **Active now**,
**Finished** (after `ends_at`), **Ended early** (`ended_at` set).

## 3. Rules

| Rule | Code |
|---|---|
| Two different people | `SAME_PERSON` |
| Nobody arranges cover that gives *themselves* access (separation of duties, same as giving access by hand) | `SELF_ASSIGNMENT` |
| Both accounts must be switched on | `ACCOUNT_INACTIVE` |
| A reason is required | `REASON_REQUIRED` (API: 400) |
| Start now or later, never in the past (5-minute grace for a slow form) | `START_IN_PAST` |
| End after the start and in the future | `INVALID_PERIOD` |
| At most `HIMS_DELEGATION_MAX_DAYS` days (default 30); arrange a new period after that | `TOO_LONG` |
| No two overlapping arrangements for the same two people | `OVERLAPPING` |
| Only the covered person's **own** current access can be lent; lent access is never lent on (no chains) | `NOT_DELEGABLE` / `NOTHING_TO_DELEGATE` |
| Roles holding `audit.view` (auditor) are never lent: auditors stay independent (ADR-013) | `NOT_DELEGABLE` |
| The person arranging it must hold every permission they lend, at that place (escalation guard) | 403 |
| Lent access never lasts longer than the original | (shortened automatically) |
| Roles the covering person already has are skipped and reported back ("Not lent: … already has this access") | — |

**Ending:**

* **Runs out:** at `ends_at` the lent access stops working by itself.
* **Ended early:** an administrator ends it with a reason (and the current `version`); every lent
  role is removed at once, including ones that had not started yet. `ALREADY_ENDED` if it has
  already ended.
* **Original removed:** if the covered person's own role is removed (Access page, access
  review, admin console), the copy lent from it is removed in the same step.
* **Account switched off:** switching off *either* person's account (leaving, suspension) ends
  their arrangements at once.
* An earlier, finished cover never blocks a new one for the same roles: its expired copies are
  closed (and recorded) when the new one is arranged.

**Administrators and lock-out:** lent administrator access never counts as one of the hospital's
administrators. So the "last administrator" protection (HIMS-IAM-015) cannot be fooled by a
temporary cover, and lent copies can always be removed.

**Two-factor:** if the lent access is privileged (e.g. HR or administrator), the covering person
must set up two-factor sign-in before using it, as for any privileged role.

## 4. Who can do what

| Action | Permission |
|---|---|
| See all arrangements (Cover page, filters) | `access.roles.view` |
| Arrange cover, end it early, see what a person can lend | `access.assignments.manage` (two-factor required) |
| See the arrangements you are part of (Security page) | Everyone signed in |
| Admin console: arrange (lends everything that can be lent), view, "End selected cover now" | Admin console + `access.assignments.manage` |

## 5. Notifications and audit

* Emails (no clinical data) to both people when cover is arranged ("you are covering for …" and
  "… is covering for you", with dates, reason and the roles lent) and when it ends early.
* Audit log: `access.delegation.created` (roles lent, roles skipped, dates),
  `access.delegation.ended`, plus the usual `access.role.assigned` / `access.role.revoked` for
  every lent role (with the arrangement's id).
* Access reviews show lent access as "Role (cover for Name until date)".

## 6. API

| Method and path | What |
|---|---|
| `GET /api/v1/access-delegations/?status=current\|past\|all&person=<id>` | Arrangements, newest first (default: current and upcoming) |
| `GET /api/v1/access-delegations/{id}/` | One arrangement with every role lent |
| `POST /api/v1/access-delegations/` | Arrange cover (`Idempotency-Key` supported). Body: `delegator`, `delegate`, `starts_at` (empty = now), `ends_at`, `reason`, `assignments` (empty = everything that can be lent). 201 with `skipped` |
| `POST /api/v1/access-delegations/{id}/end/` | End early: `version`, `reason` |
| `GET /api/v1/access-delegations/delegable/?user=<id>` | The person's own current access, `can_lend` and `why_not` for each |
| `GET /api/v1/my-delegations/` | The signed-in person's arrangements (current, and ended in the last 90 days) |
| `role-assignments` responses | New fields `delegation` and `covering_for_name` |

## 7. Not included (tracked)

* **Clinical delegation** (e.g. a consultant's patients, orders or signing rights) needs clinical
  governance sign-off on what may be delegated and to whom: **HIMS-IAM-018** (🔒 CLIN). It will
  build on this mechanism.
* **Self-service cover requests** (the away person proposes cover, an administrator approves):
  **HIMS-IAM-019** (🔓, not required by the spec; build if hospitals ask for it).
* **Emergency "break-glass" access** (spec 4.4, 13.4) is a different feature with its own rules:
  🔒 CLIN.
