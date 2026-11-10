# Before you push: the GitHub checks, run on your PC first

**Spec:** 33.1 (pull-request quality gates), 33.6 (supply chain). Workflows:
`.github/workflows/pull-request-ci.yml` and `.github/workflows/browser-tests.yml`.

Every pull request into `development` (and every push to `development`, `qa`, `staging`,
`production`) runs these checks. A PR can only be merged when the **required** ones are green.

## What GitHub runs

| Check | Required | What it does | Run it on your PC (from the HIMS folder) |
|---|---|---|---|
| **backend** | yes | Lint (`ruff check`), formatting (`ruff format --check`), Django system check, "migrations are committed", **all backend tests on PostgreSQL 17.6**, the API description is up to date (built on an **empty** database), known vulnerabilities in Python packages (`pip-audit`) | `cd backend` then `ruff check .`, `ruff format --check .`, `python manage.py check`, `python manage.py makemigrations --check --dry-run`, `python manage.py data_dictionary --check`, `python manage.py compliance_docs --check`, `pytest -q -rfE` |
| **frontend** | yes | API types match the API description, type check, lint, all unit tests, build, bundle size budget, known vulnerabilities (`npm audit`) | `cd frontend` then `npm run api:types` (no change expected), `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`, `npm run size` |
| **secret-scan** | yes | gitleaks looks at every commit of the PR for anything that looks like a password or key. Fake test passwords must look like `Synthetic-<Word>-Passw0rd-<4 digits>` (`.gitleaks.toml`); a reviewed false alarm in an old commit goes in `.gitleaksignore` | (no local tool; follow the password shape rule) |
| **playwright** (browser-tests) | not yet (HIMS-QA-002) | 36 real-browser tests in Chrome with accessibility checks | `cd frontend` then `set CI=true` and `npm run e2e` |
| **container** | yes | Builds the server image (which also collects the admin console and API docs files; a missing file fails the build, HIMS-OPS-010) and starts it with production settings (`check --deploy`). Runs after `backend` passes; shows **skipped** when backend failed or for some PR events | `python manage.py check --deploy` with production settings (see the workflow file for the variables) |

Also generated and checked: the data dictionary and diagrams (`data_dictionary --check`), the
compliance documents (`compliance_docs --check`; **never edit `docs/compliance/risk-register.md`
or `requirements-matrix.md` by hand**: change `apps/compliance/catalog.py` and regenerate).

## Why PRs failed before, and the rule each one taught

| PR | What failed | Cause | Rule now |
|---|---|---|---|
| #34 | backend: API description | A screen's code asked the database a question while the description was being built on an empty database | Code that runs while the API description is built must not query the database (`swagger_fake_view` guard) |
| #36 | backend: formatting | "1 file would be reformatted" was printed but missed among other output | Run each check **on its own** and look at its exit code |
| #36 | backend: two date tests | Tests froze the clock at 6 Nov but created users on the real clock; they broke once the real date passed 6 Nov | Set the frozen clock **before** creating anything time-dependent |
| #37 | secret-scan | Fake passwords `Synthetic-Passw0rd` did not have the allowed shape | Always `Synthetic-<Word>-Passw0rd-<4 digits>`; scan the change for look-alike secrets before pushing |
| #38 | backend: one test | "2 failed" was read as "my 2 new tests"; the other was an existing test that pins the auditor's exact permissions | Read the **name** of every failed test (`pytest -rfE`), and after any fix run the **whole** suite again |
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
