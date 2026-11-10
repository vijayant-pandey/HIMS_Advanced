# Secrets and personal details never reach a log

**Ticket:** HIMS-SEC-019 · **Spec:** 13.3 ("minimize sensitive data in logs, traces, URLs and
notifications"), 13.4 ("do not put passwords, tokens … in general-purpose application logs"),
13.5 (security test: "an integration logs a secret or sensitive patient data during an
exception"), 19.1 (security tests), 27.2 (structured logs without PHI or credentials).

## What it means

Logs are read by many people (developers, support, cloud operators) and are kept for a long time.
So no log line may ever hold:

- a **password** (right or wrong), a **sign-in link** (activation, password reset), a
  **two-factor code**, an **authenticator secret** or a **backup code**;
- this hospital's own **keys and passwords** (Django secret key, database and email passwords,
  encryption and audit-chain keys, tracing headers);
- **personal details**: names, phone numbers, email addresses, search words (for example a
  patient's name typed into a search box), or the row values the database repeats in its errors.

This also holds **when something goes wrong**. An email provider or SMS gateway that refuses a
message often repeats the message, sign-in link included, in its error. A database error repeats
the values it refused (`Key (email)=(asha@…) already exists`).

## How it is enforced

| Where | What happens |
|---|---|
| **Every log line** (API, admin console, background worker) | Written as one JSON line by `common/logging.py`. Before it is written, the message, every extra field and the error trace pass through `common/log_safety.py` (the rules are in the next table) |
| **Background worker (Celery)** | Uses the same JSON lines (`worker_hijack_root_logger=False` in `config/celery.py`). Celery's own plain-text set-up would write task arguments and errors unfiltered |
| **A request in a log line** | Written as method and path only (`POST /api/v1/auth/login/`): never the query string, headers or body |
| **Web server access log** | Path only, never the query string (already so since HIMS-PLAT-016, `config/gunicorn_conf.py`) |
| **Traces** | Addresses without query strings, database queries without values (HIMS-PLAT-016). The error text a trace keeps, and every other text in it, gets the same rules on its way out (HIMS-SEC-020; see "Known gap" below, now closed) |
| **"Last error" of a failed email/SMS** (Notifications page, admin console) | The provider's error is kept with the message's sign-in links and codes hidden, then passed through the same rules. If HIMS cannot tell which parts were secret, only the kind of error is kept (`SMTPDataError`). Older rows were cleaned by migration `notifications.0002_scrub_last_errors` |
| **Error shown to the person** | Only "An unexpected error occurred" and a reference number; never the error text (unchanged) |
| **Printed emails and SMS** (developer PC) | Printed in full in the launcher window, so links can be clicked while testing |
| **Printed emails and SMS** (any hosted environment) | Their output is the server log, so an SMS is printed without its text and with the number shortened (`+91…51`); an email is printed with links and codes hidden. Production settings switch Django's console email backend to `apps.notifications.backends.ConsoleEmailBackend` automatically |
| **Web addresses** | Passwords, sign-in tokens and codes are always sent in the request **body**, never the address (addresses end up in proxy and browser logs). A test fails if any API takes a sensitive query parameter |
| **Browser console** | The app writes nothing there (lint rule `no-console`). Sign-in links keep their secret after `#`, which the browser never sends to a server, and the page removes it from the address bar after reading it |

### What the log filter hides

| Kind | Example before | Written as |
|---|---|---|
| This hospital's own secrets, wherever they appear | `login failed for <the email password>` | `login failed for [hidden]` |
| Password inside an address | `postgres://hims:<password>@db/hims` | `postgres://hims:[hidden]@db/hims` |
| `Bearer` / `Basic` credentials | `Authorization: Bearer eyJ…` | `Authorization: [hidden] [hidden]` |
| Every value in a query string or link | `?search=Asha+Rao&page=2`, `#token=Ab12…` | `?search=[hidden]&page=[hidden]`, `#token=[hidden]` |
| `name=value` for secret or personal names | `password="…"`, `api_key: …`, `phone=…`, `text='…'` | `password="[hidden]"`, … |
| Database row values in errors | `Key (lower(email::text))=(asha@…) already exists`, `Failing row contains (…)` | `Key (lower(email::text))=([hidden]) already exists`, `Failing row contains ([hidden])` |
| Email addresses and international phone numbers | `asha@…`, `+91 98000 19051` | `[hidden]` |
| Extra fields with a secret, personal or payload name | `extra={"password": …, "email": …, "args": […]}` | `"password": "[hidden]"`, … |

Kept on purpose: identifiers and counts (`patient_id`, `user_id`, `sessions_ended`,
`status_code`), the kind of error, the reference number (`request_id`), and the path of the page
or API. These are what support needs, and they say nothing about a person by themselves.

## Rules for code (developers)

1. Log **what happened and to which record**, never the contents:
   `logger.warning("notification_failed", extra={"notification_id": …, "error_type": …})`.
2. Never put a password, token, code, key, name, phone, email or free text into a log message or
   an exception message. The filter is a **safety net**, not a licence: it cannot recognise a
   patient's name written without a label.
3. Send secrets in the request body, never in the address.
4. Do not `print()` in the backend or `console.log` in the frontend.
5. A new kind of secret (for example an SMS gateway key) goes in a setting whose name contains
   `SECRET`, `PASSWORD`, `TOKEN`, `ACCESS_KEY` or `PRIVATE_KEY`: its value is then hidden
   automatically, wherever it appears.

## The tests

| Test | What it proves |
|---|---|
| `backend/common/tests/test_secrets_never_logged.py` | The **security test** (spec 13.5). It runs the real flows with marked fake secrets while every log line is captured at the most detailed level: wrong and right password, two-factor set-up, codes and backup codes, password reset, staff invitation and first password, an email provider that refuses and repeats the sign-in link, an outside service failing during a request (with a patient's name and phone, a provider key, the database password and the secret key in its error), and a database refusing a duplicate person. Then it looks for every secret in the logs, the server output, the audit log, the stored email copies and errors, the outbox, and what the administrator and the caller are shown. A failure names the secret by label (never its value) and where it was found |
| `backend/common/tests/test_log_safety.py` | Each rule above on its own; the hospital's own secrets; harmless lines unchanged; the JSON formatter; the worker setting; printed SMS and email on a developer PC and on a server; the clean-up migration; no API takes a secret in the address |
| `frontend/src/features/notifications/NotificationsPage.test.tsx` | The "Last error" explains when parts were hidden |
| `npm run lint` | No `console` call anywhere in the app |

When the security test fails: read the label (for example `reset link in the logs`), find the
code that writes it, and change that code to log an identifier instead. Do **not** weaken the
test.

## Known gap (closed 2026-11-10 by HIMS-SEC-020)

Closed: every span now passes through `ScrubbingSpanExporter` (`common/tracing.py`) before it leaves
the process, whichever exporter is used, and every text in it gets the rules above. The security test
searches the traces too. The original note follows.

**HIMS-SEC-020:** when tracing is switched on, an error's own text is also kept in the trace
(`exception.message`). Tracing is off by default and traces are not sent anywhere yet
(HIMS-PLAT-019, waits for AWS), so it does not leak today. It must be filtered with the same rules
before traces leave this computer.
