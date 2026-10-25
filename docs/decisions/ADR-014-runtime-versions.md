# ADR-014: Runtime and toolchain versions

**Status:** Proposed. **Owner:** Engineering lead. **Review:** quarterly, and before each major
upgrade.

| Component | Version | Note |
|---|---|---|
| Python | 3.13 | |
| Django | 5.2.x (LTS) | LTS until April 2028 |
| Django REST Framework | 3.18.2 | 3.16.x has known CVEs (pip-audit) |
| PostgreSQL | 17.x | RDS for PostgreSQL 17. Developer machines may run 18 locally; CI stays on 17 so the deployed version is what gets tested. Align the CI image when RDS 18 is chosen |
| Redis | 7.4 | ElastiCache |
| Celery | 5.6 | |
| Node.js | 24 (`.nvmrc`) | |
| React | 19.3 | |
| TypeScript | 5.9.3 | 6.x/7.x are blocked by typescript-eslint / openapi-typescript peer ranges; upgrade when they support it |
| MUI | 9.x | |
| Vite | 8.x | |

Python dependencies are pinned exactly in `backend/requirements/`, and npm dependencies are pinned
exactly with `package-lock.json`. Upgrades go through a PR with the full CI suite. A hash-locked
Python lockfile is HIMS-PLAT-012.
