# ADR-004: Redis is not the source of truth

**Status:** Accepted (specification section 22)

**Decision:** Redis is for cache, short-lived coordination and broker use where appropriate.

**Reason:** Clinical and financial state must remain durable in PostgreSQL.

**In code:** sessions, idempotency records and outbox events are stored in PostgreSQL; the cache falls back to in-process memory locally.
