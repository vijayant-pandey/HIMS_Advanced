# Updating the hospital databases (migrations)

**Audience:** anyone running HIMS locally. **Applies to:** every change that adds or changes a
database table (a "migration").

## When do I need this?

- After merging a PR whose description or instructions say **"run migrate"**.
- When `git pull` brings in new files under `backend/apps/*/migrations/`.
- When the app shows an error like `relation "..." does not exist`.

Each hospital has **its own database** (spec 7, ADR-003), so **every hospital must be migrated
separately**. Today that means two databases:

| Hospital | Settings file | Database |
|---|---|---|
| 🇮🇳 India | `backend\.env` (default) | `HIMS` |
| 🇺🇸 US | `backend\.env.us` | `HIMS_US` |

## The steps (CMD), always all three blocks

```cmd
cd C:\Users\vpand\OneDrive\Desktop\HIMS\backend
.venv\Scripts\activate.bat

:: India (clears any leftover setting first)
set HIMS_ENV_FILE=
python manage.py migrate

:: US
set HIMS_ENV_FILE=.env.us
python manage.py migrate

:: Back to normal for this window
set HIMS_ENV_FILE=
```

Both `migrate` commands should list the same `Applying ... OK` lines. If the second one says
`No migrations to apply` but the first one applied something, that is expected only when the US
database was already updated earlier. When unsure, check (below).

## Why the `set HIMS_ENV_FILE=` lines matter

In CMD, `set` stays active **for the whole window** until you close it or clear it. If a window
still has `HIMS_ENV_FILE=.env.us` from earlier, a plain `python manage.py migrate` updates the
**US** database, not India. That happened once (2026-10-26): India was left without three
updates (`identity.0003`, `identity.0004`, `staff.0003`) and sign-in to the India hospital would
have failed. Clearing the setting first prevents this.

## How to check which database a window uses, and what is applied

```cmd
echo %HIMS_ENV_FILE%
```
- Prints `.env.us` → this window uses the **US** database.
- Prints `%HIMS_ENV_FILE%` or nothing → this window uses **India** (`backend\.env`).

```cmd
python manage.py showmigrations identity staff
```
`[X]` = applied, `[ ]` = missing. Run it once per hospital (with the matching `set` line) to compare.

## Adding another hospital later

Every new local deployment (e.g. `backend\.env.eu`) gets one more block:

```cmd
set HIMS_ENV_FILE=.env.eu
python manage.py migrate
```

and the final `set HIMS_ENV_FILE=` still comes last.

## Good to know

- Migrations only **add or change structure**; they never delete your hospital data unless a PR
  explicitly says so (spec 26.9: expand-and-contract changes).
- Run migrations **with the servers stopped or idle**. The launcher (`npm run dev`) does not run
  migrations by itself.
- In hosted environments (Development, QA, Staging, Production) migrations will run as a separate
  release job per hospital, never by hand (spec 28.7, 30.5; ticket HIMS-OPS-006).
