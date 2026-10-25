# ADR-005: Transactional outbox for critical asynchronous workflows

**Status:** Accepted (specification section 22)

**Decision:** Use an outbox where losing an event would affect important business or integration workflows.

**Reason:** Avoid the dual-write failure between database commit and task publication.

**In code:** `common/outbox`; design details in ADR-012.
