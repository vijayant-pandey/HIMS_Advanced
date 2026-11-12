# Before you push: the GitHub checks, run on your PC first

**Spec:** 33.1 (pull-request quality gates), 33.6 (supply chain). Workflows:
`.github/workflows/pull-request-ci.yml` and `.github/workflows/browser-tests.yml`.

Every pull request into `development` (and every push to `development`, `qa`, `staging`,
`production`) runs these checks. A PR can only be merged when the **required** ones are green.

## What GitHub runs

| Check | Required | What it does | Run it on your PC (from the HIMS folder) |
|---|---|---|---|
| **backend** | yes | Lint (`ruff check`), formatting (`ruff format --check`), Django system check, "migrations are committed", **all backend tests on PostgreSQL 17.6**, the API description is up to date (built on an **empty** database), known vulnerabilities in Python packages (`pip-audit`) | `cd backend` then `ruff check .`, `ruff format --check .`, `python manage.py check`, `python manage.py makemigrations --check --dry-run`, `python manage.py data_dictionary --check`, `python manage.py compliance_docs --check`, `python manage.py api_contracts --check`, `pytest -q -rfE` |
| **frontend** | yes | API types match the API description, type check, lint, all unit tests, build, bundle size budget, known vulnerabilities (`npm audit`) | `cd frontend` then `npm run api:types` (no change expected), `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`, `npm run size` |
| **secret-scan** | yes | gitleaks looks at every commit of the PR for anything that looks like a password or key. Fake test passwords must look like `Synthetic-<Word>-Passw0rd-<4 digits>` (`.gitleaks.toml`); a reviewed false alarm in an old commit goes in `.gitleaksignore` | (no local tool; follow the password shape rule) |
| **playwright** (browser-tests) | not yet (HIMS-QA-002) | 43 real-browser tests in Chrome with accessibility checks for the India hospital and the admin console, then 12 for a separate US hospital (HIMS-QA-003) | `cd frontend` then `set CI=true`, `npm run e2e` and `npm run e2e:us` |
| **container** | yes | Builds the **hosted image from the root `Dockerfile`**: the screens with Node, then the server (HIMS-OPS-022), and checks the screens are in it. There is no Docker on the PO's PC, so before pushing a change to the image, build the screens from a clean copy of `frontend` (`npm ci`, `npm run build`) and run `check --deploy` with `HIMS_FRONTEND_DIST` set. The server part also collects the admin console and API docs files; a missing file fails the build, HIMS-OPS-010) and starts it with production settings (`check --deploy`). Any warning fails it, so a new deploy warning needs the image check's "accepted on purpose" setting in the workflow (as `HIMS_ACCEPT_LOCAL_DOCUMENT_STORAGE` and `HIMS_ACCEPT_UNSCANNED_UPLOADS`). Runs after `backend` passes; shows **skipped** when backend failed or for some PR events | `python manage.py check --deploy` with production settings (see the workflow file for the variables) |

Also generated and checked: the data dictionary and diagrams (`data_dictionary --check`), the
compliance documents (`compliance_docs --check`; **never edit `docs/compliance/risk-register.md`
or `requirements-matrix.md` by hand**: change `apps/compliance/catalog.py` and regenerate), and the API contracts and traceability matrix (`api_contracts --check`; **never edit `docs/architecture/api-and-integrations/endpoints/` or `docs/requirements/traceability.md` by hand**: run `python manage.py api_contracts` after changing an endpoint, a test that calls one, the backlog or the PR history). A new API view needs its requirement in `common/contracts/catalog.py`; a ticket marked Done needs its record in `docs/requirements/` (HIMS-DOC-001).

## Why PRs failed before, and the rule each one taught

| PR | What failed | Cause | Rule now |
|---|---|---|---|
| HIMS-OPS-024 PR | playwright (twice) | GitHub's runner could not reach Ubuntu's servers, so installing the browser's extra fonts failed and no test ran ("Temporary failure resolving"); nothing in HIMS | The workflow falls back to installing Chrome alone; a failure that happens before any test runs is the CI machine, not the code: read the first error |
| HIMS-OPS-024 PR | backend: contracts up to date | The endpoint contracts were regenerated before the API description (`openapi.yaml`) gained the new endpoint, so its contract kept a blank ID and response; the check had passed at that moment | Order matters: build the API description first, then run `api_contracts`, then `api_contracts --check` as the very last generator step |
| (caught before the hosting analysis PR) | would have failed backend: two performance tests | The index check reads PostgreSQL's plans, and the test seed refreshed statistics for its 13 main tables only; the access query also joins roles and permissions, whose statistics were whatever earlier tests and autovacuum left, so with more tests the plan started from another index. Passed alone, failed in the full run | Tests that read query plans refresh the statistics of every table first (`ANALYZE`); a test that passes alone but fails in the full run is about shared state, so read the failure text before guessing |
| docs PR (HIMS-DOC-001) | backend: lint | Three comparisons were turned round (`PERMISSION == x.access`) to keep the word `access` away from the secret scanner, after lint had already been run; ruff's SIM300 refuses that order | A change made to satisfy one check is followed by **every** check again, lint first. Keep the scanner happy without reversed comparisons: a named property (`endpoint.needs_permission`) or a short imported name |
| (caught before the docs PR) | would have failed backend: contracts up to date | The contract generator first read live settings (rate limits, time limits); the test settings use other values, so the files written on the PC never matched in CI | Generated documents must not depend on settings, `.env` or the PC: quote the defaults written in code, and check the output under the test settings (`DJANGO_SETTINGS_MODULE=config.settings.test`) before pushing |
| (caught before #49) | would have failed backend: API description | Three new choice fields were called `kind`, `outcome` and `trigger`, names other tables already use for different choices; the description build stops on the naming warning | Give each new set of choices its own name in `ENUM_NAME_OVERRIDES` (`config/settings/base.py`), and build the description on an **empty** database before pushing |
| (caught before #49) | nothing failed | A helper script saved files with Windows line endings; Git converts them when committing, but the files on the PC differed from what is committed | After any scripted edit, check the changed files for Windows line endings and convert them back |
| #34 | backend: API description | A screen's code asked the database a question while the description was being built on an empty database | Code that runs while the API description is built must not query the database (`swagger_fake_view` guard) |
| #36 | backend: formatting | "1 file would be reformatted" was printed but missed among other output | Run each check **on its own** and look at its exit code |
| #36 | backend: two date tests | Tests froze the clock at 6 Nov but created users on the real clock; they broke once the real date passed 6 Nov | Set the frozen clock **before** creating anything time-dependent |
| #37 | secret-scan | Fake passwords `Synthetic-Passw0rd` did not have the allowed shape | Always `Synthetic-<Word>-Passw0rd-<4 digits>`; scan the change for look-alike secrets before pushing |
| #38 | backend: one test | "2 failed" was read as "my 2 new tests"; the other was an existing test that pins the auditor's exact permissions | Read the **name** of every failed test (`pytest -rfE`), and after any fix run the **whole** suite again |
| (caught before #47) | would have failed secret-scan | Names holding "passkey" or "webauthn" contain the scanner's words `key` and `auth`; nine new lines put one before `=`, `:` or `,` and a long value (a session-name constant ending in KEY set to a long text, an import list, a tracker note giving a library version with two equals signs) | Such names go after the `=`, not before; split import lists over lines; positional settings defaults; write versions as "webauthn 3.0.1" in docs. Run the pattern scan on code **and** docs |
| (caught before #47) | rule broken | A new library brought in a helper (`cbor2 6.2.1`) released 3 days earlier, against the rule that versions are at least two weeks old | After regenerating the lockfile, check the release date of **every** new line, not only the library you asked for; hold a too-new helper at an older version in `base.in` with a comment |
| (caught before #47) | would have failed backend | Two tests pin the exact two-factor status; a deliberate new field (`passkeys`) failed them | A pinned answer is updated only for a deliberate change, and the same PR says so |
| (planned before #46) | would have failed container | A new deploy warning (`hims.W002`, no real virus scanner when hosted) would stop the image check, which runs hosted settings with `--fail-level WARNING` | Add the workflow's "accepted on purpose" setting in the same change as the warning, and run `check --deploy` locally with the workflow's exact variables |
| (caught before #46) | would have failed secret-scan | A made-up sign-in token in a test (`#token=` and 20 varied characters) looked real to the scanner | Fake secrets in tests use the allowed shape `Synthetic-<Word>-Passw0rd-<4 digits>`, even inside a link |
| (caught before #46) | would have broken files on a PC | The standard anti-virus test line, written whole into a source or guide file, makes Windows' own virus protection quarantine that file | Never write it whole: build it from pieces in code, and show it in two halves in guides |
| (caught before #46) | would have failed backend | Changing a risk's text in `apps/compliance/catalog.py` made the generated risk register stale | Run `python manage.py compliance_docs` after any catalog change; never edit the register by hand |
| (caught before #45) | would have failed backend | A console rule check raised its error while saving, which gave a server error page instead of a message on the form; and a "new record?" check used `if not pk`, which is never true because a new record already has an id | Run rules in the form's `clean`, and test the refusal, not only the success. A new record is `_state.adding` |
| (caught before #45) | would have failed backend | A required field added to a console form made a test's POST invalid, so its save was refused | When adding a field to a form, search the tests for posts to that page; add the field to them, do not remove the check |
| (caught before #45) | would have failed playwright | A dropdown listing only shift names had two entries starting "Night"; and the table name "My leave" also matched "My leave balance" | Show what tells entries apart (the hours), and use exact names in tests once one name contains another |
| (caught before #44) | would have failed secret-scan | A catalog field called key, set to a long dotted message name: the word next to a long, varied value looks like a real key to the scanner | Name such fields `code`, not `key`. Scan the change for look-alike secrets before pushing, whatever the test results say |
| (caught before #44) | would have failed backend | Adding a system role, and an email column on a new table, tripped tests that pin the exact list of roles and that every email column is Restricted. Writing a date with `toISOString()` in a browser test tripped the rule against UTC dates | These guard tests are doing their job: read the name, then change the code to follow the rule. Only change a pinned list when the change is deliberate (a new role is) |
| (caught before #44) | would have failed playwright | A dialog copied the first facility into its form when it opened; if the list was still loading, the form stayed empty for good. A unit test with instant answers could not see this; a real browser did | Work out values from loading data when they are used, not once on opening. A test helper's search for links also ran two links together on one line; the emails themselves were right, which was checked by opening one |
| (caught before #44) | would have failed backend | The API trims spaces around text, so saving unchanged wording looked like a change | Compare text the way the form will send it |
| (caught before #43) | would have failed backend | A new inline section on a console page made every save of that page need the section's hidden form fields; an existing test posting the form without them saw its save silently refused | Show read-only history as a read-only **field**, not an inline. Never weaken the existing test: it found a real change in behaviour |
| (caught before #43) | would have failed playwright | A button's `aria-label` left out text the button shows ("for 3 h"), which the accessibility check refuses (voice control users say what they see) | Let the visible text be the button's name; use `aria-label` only for controls with no text |
| (caught before #42) | would have failed playwright | New console pages were added to the end of a browser test's page list; its last check looks at the page that is open, which was now a page without scripts | Add pages where the test's later checks still see the page they expect, and run the **whole** browser suite after the change |
| (caught before #41) | would have failed secret-scan | A placeholder `DJANGO_SECRET_KEY` value, and an import line `SomethingAPIView, OtherView`, look like 'key = random value' to the scanner | Placeholders like `"x" * 50`; import the module (`views as spectacular`) instead of a list of names after an `API`/`Key`/`Token` word |

## The checklist (done before every PR)

1. All backend commands above, each on its own, each with exit code 0; `pytest -q -rfE` with every
   `FAILED` line read by name.
2. API description rebuilt on an empty database with `--fail-on-warn`; frontend types regenerated;
   no unexpected change.
3. All frontend commands above.
4. Browser tests: `N passed`, nothing "did not run".
5. A look for anything shaped like a secret in the changed files.
6. After **any** fix: repeat the whole step that failed, not just one test.

Things outside our control can still fail a check: a newly published vulnerability in a package
(`pip-audit`, `npm audit`) or a GitHub outage. Those are reported as they are and fixed in their
own PR (for example, Dependabot updates, HIMS-PLAT-013).

**Lessons from 2026-11-12 (HIMS-IAM-021, HIMS-QA-004)**, caught locally by the full test run before
any push:

* A new audit area (the first part of an event name, e.g. `support.`) must also be added to the
  Audit log screen's area list, `frontend/src/features/audit/labels.ts`
  (`test_every_audit_area_is_in_the_apps_area_list`).
* Never use `date.today()` or `timezone.localdate()` outside `apps/organizations/dates.py`: "today"
  is the hospital's day, from its time zone (`test_nothing_works_out_today_on_the_utc_clock`).
* Scripts that edit files on Windows must write bytes (or `newline="
"`); `write_text` turns every
  line ending into CRLF. Git turns them back on commit (`.gitattributes`), but the diff is noisier.

