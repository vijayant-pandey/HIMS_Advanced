# Browser tests (Playwright) and accessibility checks (HIMS-QA-001)

Spec 19.2: "end-to-end tests using Playwright" and "accessibility checks". These tests drive a
real Chrome browser through HIMS like a person: they sign in with real two-factor codes, read the
invitation email, use two browsers at once (administrator and nurse), and check every main screen
with **axe**, the standard accessibility checker (WCAG 2.1 A and AA; serious or critical
problems fail the test).

## What they cover (23 tests, about 3 minutes)

| File | Flow |
|---|---|
| `auth.setup.ts` | First sign-in of the administrator and the auditor; two-factor set-up with backup codes |
| `01-sign-in.spec.ts` | Wrong password and wrong code refused; menus differ by role; signed-out people sent to sign-in |
| `02-hospital-setup.spec.ts` | Facility (duplicate code refused), department, building → floor → ward → room → beds, bed into maintenance (reason required); Numbering, Features, Hospital settings |
| `03-staff-and-access.spec.ts` | Add a nurse (invitation sent automatically), resend (old link refused), activate in her own browser, "no access yet" page with reference, give access, cover arranged and ended early, cover for yourself refused, access review |
| `04-audit-and-safety.spec.ts` | Auditor finds the nurse's visit by reference, audit integrity check, review read-only; administrator refused the audit log; remaining screens; keyboard-only menu use |

Every test runs against a **throw-away database `hims_e2e`** and its own servers (API on port
8100, app on 5180), so the normal India and US hospitals keep running untouched. All people and
passwords are synthetic.

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

It finishes with `23 passed`. If something fails, `npm run e2e:report` opens a page with a
screenshot and a step-by-step recording of the failed test.

The tests use the PostgreSQL server from `backend\.env` and create the database `hims_e2e`
there (that user needs permission to create databases). To use another server:
`set E2E_DATABASE_URL=postgres://user:password@localhost:5432/hims_e2e`. The reset command
refuses any database whose name does not start with `hims_e2e`.

## In GitHub

Workflow `browser-tests` runs on every PR into `development`, every night and on demand
(Actions → browser-tests → Run workflow). It is **not** a required check yet; add it to the
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

## Adding a test

Put it in `frontend/e2e/tests/`, use roles and visible names to find things
(`getByRole("button", { name: "Save" })`), and call `expectAccessible(page, "<screen>")` on any
new screen. Test files run in name order and share the same hospital.
