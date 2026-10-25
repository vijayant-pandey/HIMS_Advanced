# ADR-002: PostgreSQL as authoritative transactional database

**Status:** Accepted (specification section 22)

**Decision:** Use PostgreSQL for production and development.

**Reason:** ACID transactions, relational integrity, indexing and concurrency controls.

**In code:** tests run against real PostgreSQL 17 (never SQLite); constraints, partial unique indexes and triggers are part of the design.
