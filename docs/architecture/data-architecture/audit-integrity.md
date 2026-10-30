# Audit log tamper evidence (HIMS-SEC-010)

Spec 13.4 ("append-oriented audit records … restricted audit access, **tamper detection** and
monitoring of privileged access"), 4.25 (audit and governance). Decision record:
[ADR-013](../../decisions/ADR-013-audit-log-storage.md). All tables live in the hospital's own
database (one per deployment).

## 1. In plain words

The audit log already could not be changed through HIMS: a database trigger refuses every
change or delete. But someone with full control of the database server (a database
superuser) can switch triggers off. Tamper evidence makes such an edit **visible**:

1. Every audit record is *sealed* within about a minute: its fingerprint (SHA-256 over every
   field) becomes the next link of a chain.
2. Each link also covers the link before it, and is signed with a secret key that is **not**
   stored in the database (HMAC-SHA256, `HIMS_AUDIT_CHAIN_KEYS`). Someone holding only the
   database cannot rebuild the chain after editing a record.
3. Every day, and whenever an auditor presses **Check now**, the whole chain is recomputed.
   Any difference is reported on the **Audit integrity** screen and emailed to auditors.

## 2. Tables

| Table | Purpose | Key rules |
|---|---|---|
| `audit_events` (existing) | The audit log | Unchanged. Append-only trigger. |
| `audit_chain_entries` | One link per sealed audit event | `sequence` 1, 2, 3 … with no gaps; `event_id` (unique, points at the audit event); `event_hash` (SHA-256 fingerprint of the event); `previous_hash` (the previous link's `entry_hash`; 64 zeros for the first); `entry_hash` = HMAC(key, format, sequence, previous_hash, event_hash, event_id); `key_id` (name of the key, never the key); `sealed_at`. **Append-only** (database trigger + ORM). |
| `audit_integrity_checks` | Result of each check | Outcome `passed` / `failed`; trigger `scheduled` / `on_demand` / `command`; who started it; records sealed just before; records checked; last sequence and **chain head** (newest link's hash); problem count and the first 100 problems with details; records never sealed. **Append-only**. |

## 3. Sealing

* Runs every minute (Celery beat `audit-seal-events`), before every check, and on demand with
  `python manage.py seal_audit_log`. Safe to run any number of times and on several workers at
  once (a PostgreSQL advisory lock lets one seal while the others wait).
* Takes committed audit events that have no link yet, oldest first, in batches of 1,000.
* It looks back 24 hours from the newest sealed record (`HIMS_AUDIT_SEAL_LOOKBACK_HOURS`), so a
  slow transaction that commits late is still sealed. A record that appears **older** than that
  window and was never sealed is reported by the check ("never sealed"): it was written outside
  the normal path or with a back-dated time.
* The fingerprint covers every column of the event (id, time, organization, facility, actor,
  action, record, outcome, reason, reference number, IP address, browser, before/after changes,
  extra details) in a fixed JSON layout (`v1`).

## 4. The check

Runs daily (Celery beat `audit-integrity-check`), from the **Audit integrity** screen ("Check
now"), from the admin console ("Run integrity check now") and with
`python manage.py check_audit_log` (exit code 1 when problems are found, for scripts and
monitoring). Only one check runs at a time (`CHECK_RUNNING`, 409).

| Problem | Meaning |
|---|---|
| `event_changed` | The record was changed after it was sealed |
| `event_missing` | The record was deleted after it was sealed |
| `links_missing` | Links are missing (sealed records were removed together with their links) |
| `link_broken` | A link does not follow on from the one before it |
| `link_changed` | A link was changed or rebuilt without the key |
| `unknown_key` | A link was signed with a key that is no longer configured |
| `chain_cut` | The chain is shorter than at the previous check (the newest links were removed) |
| `chain_rewritten` | The link recorded by the previous check no longer matches (links were rebuilt) |
| `not_sealed` | A record older than the sealing window was never sealed |

After every check:

* the result is stored in `audit_integrity_checks` (never changed);
* the check is written to the audit log (`audit.integrity.checked`, outcome success or
  failure, with the chain head), so it is itself sealed by the next run;
* when problems are found: an email goes to every active person holding `audit.view`
  (no PHI in it, only counts and a link), the alert is audited
  (`audit.integrity.alert_sent`), and an `ERROR` log line `audit_integrity_check_failed` is
  written for monitoring.

## 5. Keys

* `HIMS_AUDIT_CHAIN_KEYS`: comma-separated `key-id:secret`, **newest first**. New links are
  signed with the first key; any listed key can check older links, so keys can be rotated by
  adding a new one at the front and keeping the old ones listed.
* Required in Development/QA/Staging/Production: the server refuses to start without it, or if
  an entry is not `id:secret` with a secret of at least 32 characters. Keep it in the secret
  manager, separate from the database credentials. Never commit it.
* Developer PCs and tests: when nothing is set, a key named `local` is derived from
  `DJANGO_SECRET_KEY`. It stays available even after a real key is added. If
  `DJANGO_SECRET_KEY` changes, older local links show `unknown_key` or `link_changed`.
* Generate a key: `python -c "import secrets; print('k1:' + secrets.token_hex(32))"`.

## 6. Who can do what

| Action | Who |
|---|---|
| See status, history and problem details; Check now (app and admin console) | `audit.view` holders (auditor / compliance role). Two-factor sign-in required. |
| Anything else | Nobody. Administrators cannot see or run checks (separation of duties, ADR-013). Nobody can edit or delete links or results (database triggers). |

## 7. API

| Method and path | What |
|---|---|
| `GET /api/v1/audit-integrity-checks/status/` | Records sealed, last sealed time, chain head, records waiting, key name, latest check |
| `GET /api/v1/audit-integrity-checks/` | The last 100 checks, newest first |
| `GET /api/v1/audit-integrity-checks/{id}/` | One check with its problems in plain words |
| `POST /api/v1/audit-integrity-checks/` | Seal and check now (201 with the result; 409 `CHECK_RUNNING`) |

## 8. What this does not cover yet (tracked)

* **An independent copy of the chain head** outside the database. Today the auditor can copy the
  chain fingerprint into a register outside HIMS (the screen suggests it). Copying it
  automatically to write-once storage (S3 Object Lock) is **HIMS-SEC-016** (🔒 AWS). Until then,
  someone holding both the database *and* the key could rebuild the whole chain.
* **A record forged in the minute before sealing** would be sealed as if genuine. The chain
  proves that nothing changed **after** sealing.
* **Very large logs**: the on-demand check runs inside the web request. When the audit log
  passes about a million records, move "Check now" to a background job with progress
  (**HIMS-SEC-017**, 🔓 when that volume is near).
* Retention and legal hold remain 🔒 LEGAL (ADR-013). When old audit records are ever removed
  under a retention policy, the chain needs a documented "archived up to link N" marker first.
