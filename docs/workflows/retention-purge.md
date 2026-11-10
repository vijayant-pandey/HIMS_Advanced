# Retention purge and legal hold (HIMS-COMP-006)

**Spec:** 4.25 ("retention, legal holds, export controls and deletion restrictions"), 13.3, 28.1 #5.
Decision record: [ADR-030](../decisions/ADR-030-retention-purge-and-legal-hold.md). Periods to choose:
[retention schedule](../compliance/retention-schedule.md).

## In one paragraph

The hospital decides how long each kind of housekeeping record is kept. A daily job deletes what is
older. **Nothing is deleted until a period is set**, a shorter period waits 7 days, and a **legal hold**
stops the purge for the records it covers. Every run is recorded with its counts.

## What can be purged

| Kind | Table | What goes | Never goes | Minimum |
|---|---|---|---|---|
| Sign-in register | `user_sessions` | Sign-ins that ended before the cut-off | Open sessions | 365 days |
| Message log (emails and SMS) | `notifications` | Sent, given-up and not-sent messages | Messages waiting or being retried | 90 days |
| Account invitations | `user_invitations` | Accepted, revoked or expired | Open invitations | 30 days |
| Password-reset requests | `user_password_resets` | Used, revoked or expired | Open requests | 30 days |
| Browser block reports | `browser_security_reports` | Days before the cut-off | — | 30 days |
| Refused console addresses | `console_access_blocks` | Reviewed days before the cut-off | Unreviewed ones | 365 days |

**Never purged here:** the audit log and its chain (needs an archive first, HIMS-COMP-007), staff
records and documents, compliance registers and incidents, backups and drills, rotas and leave, and
from Phase 2 every patient, clinical and financial record (spec 28.2).

The audit log keeps every sign-in, message and review **event**, so deleting the rows above never
removes the evidence of what happened.

## Where

- **App:** Compliance → **Retention** tab. Viewing needs `compliance.view` (e.g. Auditor). Changing
  needs `compliance.manage` (Compliance officer, Organization administrator) and **confirm it's you**.
- **Admin console:** Compliance → **Retention rules** (periods), **Legal holds** (place, release),
  **Retention purge runs** (history and **Run the purge now**).
- **Server:** `python manage.py purge_expired_records --dry-run` shows what would go;
  without `--dry-run` it deletes. The same job runs daily through Celery beat (`retention-purge`).

## Setting a period

1. Compliance → Retention → **Change** next to the kind.
2. Type the days (at least the minimum), or tick **Keep for ever**.
3. Confirm it's you if asked.

| Change | When it applies |
|---|---|
| First period, or a shorter one | After **7 days** (shown as "… from <date>"); it can be cancelled until then |
| A longer period, or Keep for ever | At once (it deletes nothing) |
| The same period as now, while a shorter one waits | Cancels the waiting one |

The **Would delete now** column shows what a purge would delete at this moment, before anything goes.

## Legal hold

Use a hold when a dispute, complaint, investigation or legal request is expected.

1. Compliance → Retention → **Place a legal hold**.
2. Give a **reference** (case or matter number) and a **reason**. Write no patient details.
3. Tick the kinds to hold (none ticked = every kind).
4. Optionally type one account's email: only the records about that person are held.
5. Confirm it's you.

While a hold is active, the purge keeps what it covers, whatever the period. **Release** it with a
reason once counsel says it can end. Holds are never deleted, and both placing and releasing are in
the audit log.

## Each run

- Waiting periods whose 7 days are over take effect first (audit: "Shorter retention period took
  effect").
- Each kind is deleted in batches of 2,000. At most 50,000 rows per kind are deleted per run; the
  rest go next time ("more next run").
- One run at a time: a second one started at the same moment is refused with "A purge is already
  running".
- Recorded in **Purge runs** (cannot be changed or deleted, database trigger) and in the audit log
  ("Retention purge run"), with counts per kind and what holds kept.

## On your PC

- No period is set, so the purge deletes nothing until you set one.
- Celery beat usually is not running on a PC; use `python manage.py purge_expired_records`.
- India and US are separate databases: set periods and holds in each.

## If something went wrong

- **Too much would be deleted:** while a shorter period is still waiting, cancel it (set the current
  period again) or place a hold on the whole kind.
- **Already deleted:** the rows can only come back from a backup ([backup and restore](backup-and-restore.md)).
  The audit log still has the events.
