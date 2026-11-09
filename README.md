# HIMS — Hospital Information Management System

Multi-hospital HIMS for the United States and India. The architecture is defined in
[HIMS_Architecture_Specification_v2.MD](HIMS_Architecture_Specification_v2.MD). Decisions are
recorded in [docs/decisions](docs/decisions/README.md) and current work in
[docs/backlog](docs/backlog/phase-1-foundation.md). Progress against the specification is in the
[tracker](docs/status/spec-status.md), and the ordered plan for every phase (done, left, blocked)
in the [roadmap](docs/status/roadmap.md). The product owner's step-by-step browser test is
[docs/testing/flow-part1.md](docs/testing/flow-part1.md).

| Path | Contents |
|---|---|
| `backend/` | Django 5.2 + DRF modular monolith, Celery workers |
| `frontend/` | React 19 + TypeScript SPA (Vite, MUI, TanStack Query) |
| `docs/api/openapi.yaml` | API contract (generated; checked in CI) |
| `docs/decisions/` | Architecture Decision Records |
| `infrastructure/` | Terraform and runbooks (Stage B onward) |

**Use synthetic data only** outside Production. Never commit secrets, patient data or real
clinical documents.

## Local development

Prerequisites: Python 3.13, Node 24 (`.nvmrc`), and PostgreSQL 17 + Redis 7. The easiest way to
get the databases is `docker compose up -d`.

```bash
# Backend
cd backend
python -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install --require-hashes -r requirements/dev.txt   # hash-locked; docs/workflows/dependencies.md
cp .env.example .env
python manage.py migrate
ADMIN_PW='choose-a-long-local-password' python manage.py provision_organization \
  --legal-name="Synthetic Health Pvt Ltd" --display-name="Synthetic Health" \
  --country=IN --timezone=Asia/Kolkata --currency=INR \
  --admin-email=admin@synthetic.test --admin-name="Synthetic Admin" --admin-password-env=ADMIN_PW
celery -A config worker -l info                 # needs Redis (not required yet)
celery -A config beat -l info

# Frontend
cd frontend
npm ci
```

## Everyday use: one command

```cmd
cd frontend
npm run dev
```

This opens the **launcher** at http://localhost:5173. Pick a hospital deployment and the
launcher starts its Django backend and React app in the background, then redirects you.
Ctrl+C in that terminal stops everything it started.

| Deployment | App | API / admin | Backend env file | Database |
|---|---|---|---|---|
| India | http://localhost:5175 | http://localhost:8000/admin/ | `backend/.env` | `HIMS` |
| US | http://localhost:5174 | http://localhost:8001/admin/ | `backend/.env.us` | `HIMS_US` |
| Europe | planned | — | — | — |

Each hospital organization has its own deployment and database (ADR-003). To add another
local deployment, create `backend/.env.<x>` (own `HIMS_DEPLOYMENT_ID`, database and cookie
names), run `migrate` and `provision_organization` with `HIMS_ENV_FILE=.env.<x>`, add a
`frontend/.env.<x>` Vite mode file, and register it in `frontend/scripts/dev-launcher.mjs`.

Manual equivalent of the launcher (CMD, one terminal per process):

```cmd
:: India                                         :: US
cd backend                                       cd backend
.venv\Scripts\activate.bat                       .venv\Scripts\activate.bat
python manage.py runserver                       set HIMS_ENV_FILE=.env.us
                                                 python manage.py runserver 8001
cd frontend && npm run dev:in                    cd frontend && npm run dev:us
```

## Two-factor sign-in (MFA)

Privileged accounts (administrators, auditors, HR/credentialing, facility administrators) must
set up two-factor sign-in with an authenticator app at their next sign-in (ADR-018). On a
developer machine only, it can be switched off temporarily by adding
`HIMS_MFA_REQUIRED_FOR_PRIVILEGED=false` to `backend/.env`; production refuses to start like that.
Managed environments must set `HIMS_FIELD_ENCRYPTION_KEYS` (see `common/crypto.py`) and
`HIMS_AUDIT_CHAIN_KEYS` (audit tamper evidence; see `apps/audit/integrity.py`) and
`HIMS_TRUSTED_PROXIES` (real client addresses; see `docs/workflows/security-headers.md`).

## Logs never hold secrets

Every log line is JSON and passes a filter that hides passwords, sign-in links, codes, keys and
personal details, and a security test runs the real flows to prove nothing leaks (HIMS-SEC-019).
Log identifiers and outcomes, never contents: see
[docs/workflows/log-safety.md](docs/workflows/log-safety.md).

## Backups and restore drills

On a developer PC, `python manage.py backup_database` backs up the database and documents, and
`python manage.py restore_drill` restores the newest backup into a separate copy and checks every
record, the audit chain and every document (also on the **Backups** page). Needs PostgreSQL's
`pg_dump`/`pg_restore`; backups hold every record, so keep `backend/backups/` private (HIMS-OPS-009):
see [docs/workflows/backup-and-restore.md](docs/workflows/backup-and-restore.md).

## Separate database users

The app connects with its own limited database user: it can never change, delete or empty the audit
log, and only `migrate` uses the owner (HIMS-OPS-007). Set it up once per hospital with
`python manage.py setup_database_roles --write-env` and check with
`python manage.py check_database_roles`: see
[docs/workflows/database-users.md](docs/workflows/database-users.md).

## Background jobs and runbooks

Work done just after a change (emails, follow-ups) goes through the outbox: retried by itself,
cleaned up daily, and shown on the **Background jobs** page, where an administrator sends a failed
event again or dismisses it, with a reason (HIMS-PLAT-014). `python manage.py outbox_status` gives
the same numbers. What to do when something goes wrong: [docs/runbooks](docs/runbooks/README.md).

## Static files in hosted environments

The admin console's and API docs' style and script files are collected into the server image and
served by the app itself (WhiteNoise); Swagger UI is bundled, not loaded from a CDN (HIMS-OPS-010):
[docs/workflows/static-files.md](docs/workflows/static-files.md). After pulling a change that adds a
library, run `pip install --require-hashes -r requirements/dev.txt` in `backend`.

## Decisions and hosting

Approvals from the PO, clinical and legal reviewers are kept in the
[decisions log](docs/status/decisions-log.md). Hosting will be on Oracle Cloud at the end of the
build ([ADR-027](docs/decisions/ADR-027-hosting-on-oracle-cloud.md)).

## Updating the databases after a merge

When a change includes database migrations, **every hospital database must be updated**. Follow
[docs/workflows/database-migrations.md](docs/workflows/database-migrations.md): it always runs
India, then US, and clears `HIMS_ENV_FILE` so no database is skipped.

## Quality gates (run before every PR)

```bash
cd backend  && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && pytest
cd frontend && npm run typecheck && npm run lint && npm test && npm run build
```

The full list GitHub runs (also the API description, data dictionary, compliance documents, bundle
size, secret scan and browser tests), how to run each one locally, and why earlier PRs failed:
[docs/workflows/before-you-push.md](docs/workflows/before-you-push.md).

When the API changes, regenerate the contract and the frontend types:

```bash
cd backend  && python manage.py spectacular --file ../docs/api/openapi.yaml --validate --fail-on-warn
cd frontend && npm run api:types
```

## Branching and release

Environment branches (ADR-017): `development` → `qa` → `staging` → `production`.

1. On `development`: `git pull origin development`, then code
2. `git switch -c feature/HIMS-123-short-description` (uncommitted changes move with you)
3. `git add -A`, `git commit -m "..."`, `git push -u origin feature/...`
4. On GitHub: open a PR into `development`, wait for the 4 checks, then **Squash and merge**
5. Back on `development`: `git pull origin development`
6. Promote with PRs `development`→`qa`→`staging`→`production` using **Create a merge commit**
   (never squash a promotion PR)

Never commit directly on `development`, `qa`, `staging` or `production`. Fixes found in QA or
Staging go through a new feature branch from `development`.
