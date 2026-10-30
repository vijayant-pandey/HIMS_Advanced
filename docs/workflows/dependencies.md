# Adding or upgrading a library (HIMS-PLAT-012)

HIMS installs **exactly** the reviewed versions of every library, checked by a checksum
(spec 32.5, 33.3). If a library on the internet was changed or replaced, installation stops.

## The files

| File | What it is | Edit by hand? |
|---|---|---|
| `backend/requirements/base.in` | Libraries the running app needs, with exact versions | **Yes** |
| `backend/requirements/dev.in` | Extra tools for developers and CI (tests, lint, audit) | **Yes** |
| `backend/requirements/base.txt` | The lockfile: every library incl. indirect ones, with checksums | **No**, generated |
| `backend/requirements/dev.txt` | Same for the developer tools | **No**, generated |
| `frontend/package-lock.json` | The same idea for the frontend (npm writes it) | **No** |
| `.nvmrc`, `backend/.python-version` | The exact Node and Python versions | Yes, in an upgrade PR |

## After pulling a change that touched requirements

In CMD:

```
cd C:\Users\vpand\OneDrive\Desktop\HIMS\backend
.venv\Scripts\activate.bat
pip install --require-hashes -r requirements/dev.txt
cd ..\frontend
npm ci
```

## Adding or upgrading a Python library

1. Choose a version that is **at least two weeks old** (newer only for a security fix).
2. Change or add the line in `base.in` (or `dev.in` for a tool only developers need).
3. Regenerate both lockfiles (in `backend\requirements`, virtual environment on):
   ```
   uv pip compile base.in --universal --generate-hashes --python-version 3.13 -o base.txt
   uv pip compile dev.in --universal --generate-hashes --python-version 3.13 -o dev.txt
   ```
4. Install and check:
   ```
   cd ..
   pip install --require-hashes -r requirements/dev.txt
   pip-audit -r requirements/base.txt
   pip-audit -r requirements/dev.txt
   pytest -q
   ```
5. Commit the `.in` and `.txt` files together in one PR. The test
   `common/tests/test_dependencies.py` fails if they don't match.

`--universal` makes one lockfile that works on Windows (your PC) and Linux (CI and servers).

## Adding or upgrading a frontend library

`npm install <name>@<exact version> --save-exact` in `frontend`, then `npm audit` and the
frontend checks. Commit `package.json` and `package-lock.json` together. Keep the first
download small: CI fails if any JavaScript file is over 500 kB (`npm run size`). Load large
libraries only on the screens that need them.
