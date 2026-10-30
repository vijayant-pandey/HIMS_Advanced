# Access reviews and sign-in register (HIMS-IAM-012, HIMS-IAM-016)

Spec 4.4 ("periodic access reviews"), 13.2 ("periodic permission review and prompt termination of
access"), 13.5 (sessions). All tables live in the hospital's own database (one per deployment).

## 1. Tables

| Table | Purpose | Key rules |
|---|---|---|
| `access_reviews` | One periodic review | Status `open` → `completed` or `cancelled`. **Only one open review** per hospital (partial unique index). `version` for safe concurrent edits. Never deleted. |
| `access_review_items` | One person's role at one place, copied when the review started | Copies person name, email, account on/off, last sign-in, role name and place, so the evidence still reads correctly after renames. Points at the real `role_assignments` row. Decision `pending` / `keep` / `remove` / `ended`. Unique per review and assignment. |
| `access_review_reminders` | Each reminder email sent | Unique per hospital, kind (`due`, `overdue`) and date, so the daily job never sends the same reminder twice. |
| `user_sessions` (existing) | Register of sign-ins | New end reason `signed_out_by_user` ("Signed out by the person from another device"). |

## 2. Rules

* **Start**: copies every role assignment that gives access right now (not revoked, started,
  not expired). Finish-by date defaults to 14 days and cannot be in the past.
* **Keep / remove**: reviewers need `access.reviews.manage`. Several entries can be decided at
  once (up to 500). **Remove** needs a reason; it revokes the assignment through the same service
  as the Access page (`revoke_role_assignment`) in the same transaction, so access ends
  immediately and the role revocation is audited too. A removed entry cannot be changed back
  (give the access again on the Access page if needed).
* **Own access**: nobody decides on their own entries (`SELF_REVIEW`).
* **Already ended**: if the access ended elsewhere (for example the person left), the entry is
  marked `ended` instead of kept or removed.
* **Last administrator**: the hospital's last organization administrator role cannot be removed
  (`LAST_ADMINISTRATOR`), here or anywhere else.
* **Complete**: only when no entry is `pending`; needs the current `version`; the review is then
  locked. **Cancel**: needs a reason; decisions already made stay.
* **Schedule**: next review due `HIMS_ACCESS_REVIEW_INTERVAL_DAYS` (default 90) after the last
  completed one (or after the hospital was set up). The daily job
  (`notifications.access_review_reminders`, or `python manage.py send_access_review_reminders`)
  emails everyone with `access.reviews.manage` when a review is due, and again once when the open
  review passes its finish-by date.

## 3. Audit events

`access.review.started`, `access.review.decided` (kept / removed / already ended counts and the
entries), `access.review.completed`, `access.review.cancelled`, `access.review.exported` (CSV
download), `access.review.reminder_sent`, plus the normal `access.role.revoked` for every removal.
"My sign-ins" uses `auth.sessions.ended` with reason `signed_out_by_user`.

## 4. API

| Method and path | Permission |
|---|---|
| `GET /access-reviews/`, `GET /access-reviews/{id}/`, `GET /access-reviews/{id}/items/?decision=&search=` | `access.reviews.view` |
| `GET /access-reviews/schedule/`, `GET /access-reviews/{id}/export/` (CSV) | `access.reviews.view` |
| `POST /access-reviews/` (Idempotency-Key), `POST /access-reviews/{id}/decide/`, `/complete/`, `/cancel/` | `access.reviews.manage` |
| `GET /auth/sessions/`, `POST /auth/sessions/{id}/sign-out/`, `POST /auth/sessions/sign-out-others/` | signed in (own sessions only) |

The admin console has the same controls: Access reviews (start; complete or cancel selected),
Access review items (keep or remove selected, same rules) and the reminders log (read only).
