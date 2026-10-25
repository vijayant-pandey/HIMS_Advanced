# ADR-010: Celery broker — Redis now, SQS evaluated before production

**Status:** Proposed. **Owner:** Architecture + Operations. **Review:** before the Stage C pilot.

## Context
Spec 6.2 and 14.3 start with Redis as the broker and ask for RabbitMQ or managed messaging to be
evaluated when durability or routing needs grow. With the Redis transport, unacknowledged tasks
are redelivered after a visibility timeout, and long or ETA tasks can run twice. A Redis failover
can also lose in-flight messages.

## Decision
- Use Redis (ElastiCache) as the broker for local, Development and QA.
- Critical work never depends on the broker alone: it is written to the PostgreSQL outbox in the
  business transaction (ADR-005/012). A lost broker message is republished or replayed from the
  outbox, and consumers deduplicate.
- Celery is configured with `acks_late`, `reject_on_worker_lost`, prefetch 1, JSON-only payloads,
  time limits, and per-deployment queue names.
- **Before the production pilot**, evaluate Amazon SQS as the broker (managed, durable, per-customer
  queues, no cluster to run). Compare on cost per customer, failure behaviour and operational
  load, and record the outcome here.

## Consequences
- Broker choice can change without changing domain code, because tasks are routed by name.
- Do not use Celery ETA/countdown for clinically meaningful scheduling (e.g. medication due
  times). Persist schedules in PostgreSQL and poll them.
