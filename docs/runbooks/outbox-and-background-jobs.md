# Runbook: background jobs (outbox) stuck or failing

**Ticket:** HIMS-PLAT-014 · **Spec:** 14.2 (transactional outbox), 14.3 ("monitor queue depth,
task age, retries and exhausted-retry cases"), 27.2 (runbooks) · **Decision:**
[ADR-012](../decisions/ADR-012-outbox-dispatcher.md)

## What this is about

Some work happens just after a change is saved: for example a new member of staff gets an
invitation email, a password reset sends its link. The change and a note of the work to do (an
**event**) are saved together, so nothing is lost. A dispatcher then does the work. If it fails,
HIMS retries by itself, waiting longer each time (`HIMS_OUTBOX_MAX_ATTEMPTS`, default 12). Only an
event that fails every retry needs a person.

| Where to look | What it shows |
|---|---|
| App → **Background jobs** (`platform.jobs.view`, administrator) | Waiting, oldest waiting, being retried, failed, done in 24 hours, last clean-up; the events that need a look, with **Send again** and **Dismiss** |
| `python manage.py outbox_status` | The same numbers; exits with an error when something needs a look (for monitoring) |
| Server log | `outbox_attention_needed` (checked every 15 minutes), `Outbox event exhausted publish retries`, `outbox_cleaned_up` |
| Admin console → Outbox events | Every event, filter by status; "Send selected … again" |
| Audit log → area **Background jobs** | Every clean-up and every decision, with who and why |

## Owner

The hospital's **system administrator** (organization administrator role). Escalation: the HIMS
support engineer on call.

## Impact

| Signal | What people notice | Urgency |
|---|---|---|
| Failed invitation or password-reset events | The person never gets their email, so cannot sign in | Same day |
| Many events waiting, oldest older than 15 minutes | Emails late; other follow-up work late | Within the hour |
| Waiting count keeps growing | The dispatcher or the background worker is down | Now |

No record is lost in any of these cases: the change itself was saved, only the follow-up work is
late. Nothing clinical depends on these events yet (spec 14.3: never perform irreversible clinical
actions merely because a scheduled task ran).

## First checks (5 minutes)

1. **Background jobs** page: is it "failed" (a few events, same kind) or "waiting" (many, growing)?
2. Look at **Last error** on the failed events. It shows the kind of error only, e.g.
   `ConnectionError`, `SMTPAuthenticationError`.
3. **Messages** page (notifications): are emails failing too? Then it is the email server, not
   the outbox.
4. Is the background worker running? On a developer PC without Redis the events are handled at once
   inside the app (inline mode); a "waiting" event there means its handler failed.
5. `python manage.py outbox_status` for the same numbers from the command line.

## Safe fixes

| Situation | Do |
|---|---|
| Email server or another service was down and works again | **Send again** each failed event, reason e.g. "Email server fixed 10:30". It gets a fresh set of retries |
| Many events waiting because the worker or dispatcher is stopped | Start it again (`celery -A config worker`, `celery -A config beat`, or `python manage.py run_outbox_dispatcher`). Waiting events are picked up by themselves; do **not** send them again one by one |
| An event can never succeed (what it was about no longer exists, e.g. a test account that was removed) | **Dismiss** it with the reason. It is never tried again |
| Same event fails again after "Send again" | Stop sending it again. Escalate with the event's reference (its id) and the error |

Sending an event again is safe even if part of its work already happened: each handler records
that it has run, so its database effects happen at most once (ADR-012). An email may be sent twice
in the worst case.

**Never** delete events or change them in the database by hand; that removes the evidence of
what happened.

## Escalation

Escalate to the HIMS support engineer when: the same failure repeats after a fix; more than 50
events are waiting for more than an hour; or the error kind is unknown (`IntegrityError`,
`ProgrammingError`, anything not about a network or mail server). Give: the time, the
**Background jobs** numbers, the event references and the error kinds. Never send patient or
personal details in the escalation (spec 32.2).

## Communication

Tell the people affected (for example HR, whose new starters did not get their invitation) what
happened and when it will be sent. For an outage longer than an hour, inform the hospital's
operations lead.

## Recovery check

- **Background jobs** shows "Everything is flowing: nothing needs a look".
- `python manage.py outbox_status` ends with `OK`.
- The people affected confirm they received their email (or the **Messages** page shows it sent).

## Review afterwards

For any outage longer than an hour, or any dismissed event that affected a person: write down
what failed, why the retries did not cover it, and whether monitoring should have caught it
sooner (alarms come with hosting, HIMS-OPS-004). Record it as a security incident only if data
could have been exposed.

## Clean-up (automatic)

Every day the scheduler deletes **published** and **dismissed** events older than
`HIMS_OUTBOX_RETENTION_DAYS` (default 30), in small batches, together with the duplicate-check
markers of events that can no longer run again. **Waiting and failed events are never deleted
automatically.** Each clean-up is in the audit log with the number deleted. To run it now:
`python manage.py outbox_cleanup`.

| Setting | Default | Meaning |
|---|---|---|
| `HIMS_OUTBOX_MAX_ATTEMPTS` | 12 | Retries before an event counts as failed |
| `HIMS_OUTBOX_STUCK_MINUTES` | 15 | A waiting event older than this needs a look |
| `HIMS_OUTBOX_RETENTION_DAYS` | 30 | Finished events kept this long |
