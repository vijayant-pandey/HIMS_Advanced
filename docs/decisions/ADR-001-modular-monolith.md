# ADR-001: Modular monolith before microservices

**Status:** Accepted (specification section 22)

**Decision:** Start with a Django modular monolith and Celery workers.

**Reason:** Strong transactions, simpler deployment and fewer distributed failure modes.

**Revisit when:** Domain ownership, independent scaling or reliability needs justify service extraction.

**In code:** one Django project; domains under `backend/apps/`; each app keeps `models`, `selectors` (reads), `services` (transactions) and `api/` (spec 8.1).
