# Browser tests (Playwright) and accessibility checks (HIMS-QA-001, HIMS-QA-003)

Spec 19.2: "end-to-end tests using Playwright" and "accessibility checks". These tests drive a
real Chrome browser through HIMS like a person: they sign in with real two-factor codes, read the
invitation email, use two browsers at once (administrator and nurse), and check every main screen
with **axe**, the standard accessibility checker (WCAG 2.1 A and AA; serious or critical
problems fail the test).

## What they cover (43 tests for India and the console, about 6 minutes; 12 for the US hospital)

| File | Flow |
|---|---|
| `auth.setup.ts` | First sign-in of the administrator and the auditor; two-factor set-up with backup codes |
| `01-sign-in.spec.ts` | Wrong password and wrong code refused; menus differ by role; signed-out people sent to sign-in |
| `02-hospital-setup.spec.ts` | Facility (duplicate code refused), department, building → floor → ward → room → beds, bed into maintenance (reason required); Numbering, Features, Hospital settings |
| `03-staff-and-access.spec.ts` | Add a nurse (invitation sent automatically), resend (old link refused), activate in her own browser, "no access yet" page with reference, give access, cover arranged and ended early, cover for yourself refused, access review; rota and leave: the nurse is posted, gets a night shift, asks for that day off, the administrator approves and the shift is cancelled |
| `04-audit-and-safety.spec.ts` | Auditor finds the nurse's visit by reference, audit integrity check, review read-only; administrator refused the audit log; remaining screens; security incident; no screen blocked by the browser protection rules and injected code is, with its report reviewed; a sensitive action asks, a wrong password is refused, and the action finishes by itself; audit download asks; admin console under its rules and its confirm page; keyboard-only menu use |
| `05-admin-console.spec.ts` (HIMS-QA-003) | The admin console itself: a wrong authenticator code refused; the auditor sees only the audit log and cannot add or change anything; a facility changed in the console shows in the app and as "Admin console: facility changed" in the audit log, with no delete button; the index check run in the console shows on the app's Performance screen, and the app's own button does the same |
| `06-patients.spec.ts` (HIMS-PAT-001, 2026-11-12) | The administrator makes the nurse the front desk; she registers a patient with an age, a mobile and an Aadhaar number; the record opens with its MRN and the number masked (never shown whole); the same number on a second patient is refused naming the first MRN; the administrator finds the patient but has no Register button. Accessibility checked on Patients, Register and the record |

**The US hospital (HIMS-QA-003):** `npm run e2e:us` runs a second, separate hospital in the United
States: its own throw-away database `hims_e2e_us`, API on port 8110 and app on 5190, provisioned with
country US, time zone America/New_York and dollars. `us/01-us-hospital.spec.ts` checks what differs:
hospital settings show the US, Eastern time and USD; US insurance is offered and India's ABDM and TPAs
are not; a new facility starts in the US and Eastern time; a nurse is offered US qualifications (BSN,
not B.Sc. Nursing) and a state licence, activates her account and signs in; a security incident with
personal data gets the HIPAA deadlines and not CERT-In; the compliance list shows HIPAA and not DPDP;
the auditor finds it all in the US audit log; and the US hospital's own console answers. The sign-in
set-up (`auth.setup.ts`) is shared.

Every test runs against a **throw-away database `hims_e2e`** and its own servers (API on port
8100, app on 5180, served from a production build like hospitals get), so the normal India and
US hospitals keep running untouched. All people and passwords are synthetic. There are no
retries: the tests are one story on one hospital, so a failure is investigated, not retried.

## Run them on your PC (CMD)

Once (installs the Chrome that Playwright uses):

```
cd C:\Users\vpand\OneDrive\Desktop\HIMS\frontend
npx playwright install chromium
```

Each time:

```
cd C:\Users\vpand\OneDrive\Desktop\HIMS\frontend
npm run e2e
```

It finishes with `43 passed` (about 6 to 7 minutes). Then the US hospital:

```
npm run e2e:us
```

It finishes with `12 passed` (about 2 minutes). If something fails, `npm run e2e:report` opens a
page with a screenshot and a step-by-step recording of the failed test.

The tests use the PostgreSQL server from `backend\.env` and create the database `hims_e2e`
(US: `hims_e2e_us`) there (that user needs permission to create databases). To use another server:
`set E2E_DATABASE_URL=postgres://user:password@localhost:5432/hims_e2e`. The reset command
refuses any database whose name does not start with `hims_e2e`.

## In GitHub

Workflow `browser-tests` runs on every PR into `development`, every night and on demand
(Actions → browser-tests → Run workflow). It runs the India hospital, then the US hospital. It is **not** a required check yet; add it to the
branch ruleset when you want failures to block merging. On failure the report is attached to the
run for 7 days.

## Problems these tests found and fixed (2026-10-30)

- Turning on two-factor never showed the one-time **backup codes** (the screen changed before
  they appeared).
- Opening a newer invitation or reset link in the same tab stayed on "link not valid".
- Text contrast below WCAG AA on: the highlighted menu item; the Green and Orange themes' menu
  text; blue "info" and orange "warning" status chips (all themes). A unit test now checks every
  theme.
- Loading bars had no name for screen readers.

## Problems found by the US and console tests (HIMS-QA-003, 2026-11-10)

- In a US hospital, **New facility** started with country India and time zone Asia/Kolkata. It now
  starts in the hospital's own country and time zone (United States, America/New_York).

## Adding a test

Put it in `frontend/e2e/tests/` (the US hospital: `frontend/e2e/us/`), use roles and visible names to find things
(`getByRole("button", { name: "Save" })`), and call `expectAccessible(page, "<screen>")` on any
new screen. Test files run in name order and share the same hospital.
