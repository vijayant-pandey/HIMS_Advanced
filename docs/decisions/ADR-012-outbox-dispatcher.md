# ADR-012: Outbox dispatcher and consumer deduplication

**Status:** Proposed. **Owner:** Architecture.

## Decision
- **Write:** `publish_event()` inserts into `outbox_events` and refuses to run outside a
  transaction. The envelope follows spec 29.7 (`event_id`, `event_type`, `event_version`,
  `customer_id`, `aggregate_*`, `correlation_id`, `causation_id`, minimal ID-only payload).
- **Dispatch:** `dispatch_pending()` claims pending rows with `SELECT … FOR UPDATE SKIP LOCKED` in
  batches, publishes each to the broker and marks it `published`. Failures back off
  exponentially with jitter. After `HIMS_OUTBOX_MAX_ATTEMPTS` the row becomes `dead` and an error
  is logged for alerting. Dispatch runs from Celery beat (every 5 s) and/or the long-running
  `run_outbox_dispatcher` command (a dedicated ECS service). Concurrent dispatchers are safe.
- **Delivery is at-least-once.** A crash between broker publish and commit republishes the event.
- **Consume:** `outbox.handle_event` runs every handler registered for the event type. Each
  handler runs in a transaction together with a `outbox_processed_events (handler, event_id)`
  row, so its database effects happen at most once. Handlers whose external side effects cannot
  be repeated must reconcile with the provider before acting (spec 14.3, 29.6).
- **Ordering** is not guaranteed across events, so handlers must tolerate reordering. If a
  workflow needs per-aggregate ordering, add sequence numbers to that aggregate's events rather
  than relying on the queue.

- **Inline mode (local development only).** When no broker is configured
  (`HIMS_OUTBOX_DISPATCH_INLINE`, default on when `REDIS_URL` is empty), each event is processed
  in-process right after its transaction commits. A failure leaves the event `pending` for a later
  dispatcher run. Handler deduplication is unchanged, so this never causes double processing.
  Managed environments run with a broker and the normal dispatcher.

## Follow-ups
Alarms on oldest pending age, dead count and dispatch lag (HIMS-OPS-004); retention and archival
of published rows (HIMS-PLAT-014).

## Update 2026-11-08 (HIMS-PLAT-014): clean-up, health and decisions on failed events
- Daily clean-up deletes published and dismissed events after `HIMS_OUTBOX_RETENTION_DAYS` (30)
  in small batches, with the duplicate-check markers of events that can no longer run again.
  Waiting and failed (`dead`) events are never deleted automatically.
- New status `dismissed`: a person closes a failed event that can never succeed. "Send again"
  gives a failed or stuck event a fresh set of retries. Both need a reason and are audited.
- Health (waiting, oldest age, retrying, stuck, failed) on the Background jobs page and in
  `outbox_status`; a warning line every 15 minutes when something needs a look. Alarms on it come
  with hosting (HIMS-OPS-004). Runbook:
  [background jobs](../runbooks/outbox-and-background-jobs.md).
