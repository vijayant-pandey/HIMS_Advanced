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
python manage.py runserver                      # API on :8000, docs at /api/docs/
celery -A config worker -l info                 # needs Redis
celery -A config beat -l info

# Frontend
cd frontend
npm ci
npm run dev                                     # http://localhost:5173 (proxies /api to :8000)
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
