# HIMS — Hospital Information Management System

Multi-hospital HIMS for the United States and India. The architecture is defined in
[HIMS_Architecture_Specification_v2.MD](HIMS_Architecture_Specification_v2.MD). Decisions are
recorded in [docs/decisions](docs/decisions/README.md) and current work in
[docs/backlog](docs/backlog/phase-1-foundation.md).

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
pip install -r requirements/dev.txt
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

## Quality gates (run before every PR)

```bash
cd backend  && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && pytest
cd frontend && npm run typecheck && npm run lint && npm test && npm run build
```

When the API changes, regenerate the contract and the frontend types:

```bash
cd backend  && python manage.py spectacular --file ../docs/api/openapi.yaml --validate --fail-on-warn
cd frontend && npm run api:types
```

## Branching and release

`feature/HIMS-123-…` → PR to `develop` → auto-deploy Development → release candidate → QA →
Staging → Production. The **same image digest** is promoted through every stage (spec 31–33).
