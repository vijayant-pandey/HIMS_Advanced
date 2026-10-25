# ADR-017: Interim hosting on Render + Vercel and branch-per-environment promotion

**Status:** Proposed by the product owner. Deviates from spec sections 17, 30, 31.5 and 32.6,
which remain the target architecture. **Owner:** Product owner + Engineering lead.
**Review:** before any real patient data is stored, and before the first hospital contract.

## Context
The specification targets AWS (ECS, RDS, ElastiCache) and promotes **one immutable image** through
Development → QA → Staging → Production. The product owner wants to start with managed platforms
that are faster to set up: **Render** for the Django backend (with Render PostgreSQL) and
**Vercel** for the React frontend. Promotion happens through pull requests between long-lived
branches.

## Decision
- **Four environment branches**, each one auto-deploying its own environment:

  | Branch | Environment | Backend | Frontend |
  |---|---|---|---|
  | `development` | Development | Render service + own database | Vercel (branch domain) |
  | `qa` | QA | Render service + own database | Vercel (branch domain) |
  | `staging` | Staging | Render service + own database | Vercel (branch domain) |
  | `production` | Production | Render service + own database | Vercel production |

  The names `development`/`production` replace the spec's `develop`/`main` (spec 32.4) at the
  product owner's request.

- Work flows `feature/HIMS-xxx-…` → PR into `development` → PR `development`→`qa` → PR
  `qa`→`staging` → PR `staging`→`production`. Every PR runs the full CI suite. Promotion PRs
  must contain only already reviewed commits; fixes always enter through `development` (or
  `hotfix/*` from `production`, merged back down to `staging`, `qa` and `development`).
- Feature PRs into `development` are squash-merged; promotion PRs use merge commits so the
  environment branches share history and do not drift.
- Each environment has its **own database, secrets and `HIMS_ENVIRONMENT`**. The startup guard
  (`HIMS_DATABASE_ENVIRONMENT` must match) still prevents cross-environment database use.
- Each hospital organization still gets its own backend service and database per environment
  (ADR-003). India and US are separate Render services.
- The Vercel frontend proxies `/api/*` to its Render backend (rewrites), so the browser sees one
  origin and the session/CSRF design (ADR-011) is unchanged.

## Trade-offs accepted
- Branch-based deploys **rebuild per environment** instead of promoting one image (spec 33.3).
  Mitigation: pinned dependencies and lockfiles; record the commit SHA deployed to each environment.
- **Compliance is not established.** Before real PHI: confirm a HIPAA BAA is available on the
  chosen Render/Vercel plans (US), and check data residency for India (DPDP/ABDM; Render has no
  India region at the time of writing). Until then, use **synthetic data only** in every environment.
- Cost: four environments × two hospitals means up to 8 backend services and 8 databases. Starting
  with Development + Production and adding QA/Staging when needed is cheaper (spec 34.4).
- Branch protection on private repositories requires a paid GitHub plan (Pro/Team).

## Revisit
Move to the AWS target (ADR-003, Artifact C) when compliance requirements, hospital contracts or
scale require it. The application is container-ready (Dockerfile), so the move is an
infrastructure change, not a rewrite.
