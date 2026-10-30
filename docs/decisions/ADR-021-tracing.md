# ADR-021: OpenTelemetry tracing, off by default and PHI-safe

**Status:** Proposed. **Owner:** Engineering lead. **Ticket:** HIMS-PLAT-016.
**Spec:** 6 / 18 ("OpenTelemetry-compatible tracing"), 27.2 (critical paths emit logs, metrics
and traces with a correlation/request ID, without PHI), 29.1 (no PHI or tokens in URLs or
traces), 17 (AWS observability services).

## Decision
- Use the OpenTelemetry SDK with the Django, psycopg, Celery and urllib3 instrumentations
  (`common/tracing.py`). One switch per environment: `HIMS_TRACING_EXPORTER` = `none`
  (default) | `console` | `otlp`; `HIMS_TRACING_SAMPLE_RATIO` (default 1.0); collector address
  from the standard `OTEL_EXPORTER_OTLP_*` variables. Invalid values stop start-up.
- Start-up points: `config/wsgi.py` (API, before the middleware is loaded) and Celery's
  `worker_process_init` (each worker process, because exporters do not survive a fork).
- Each span's resource carries `service.name` (`hims-api` / `hims-worker`), `service.version`
  (`HIMS_RELEASE`), `deployment.environment.name` and `hims.deployment_id`, so one collector can
  serve every hospital deployment without mixing them up.
- **Correlation:** API spans carry `hims.request_id` (the reference number users see on error
  screens and auditors search for). Every JSON log line written inside a span carries
  `trace_id` and `span_id`.
- **PHI safety:** URLs are recorded without query string, fragment or credentials (inbound and
  outbound); `url.query` is replaced; SQL is recorded with placeholders only (no values, no SQL
  commenter); no bodies, headers or user details; health checks are not traced.
- Production gunicorn access logs (`config/gunicorn_conf.py`) record the path only, never the
  query string or referring page, and include the reference number (gap found while testing).

## Consequences
- Off by default: developer PCs, tests and existing deployments behave exactly as before.
- Sending traces to AWS (ADOT collector sidecar to X-Ray/CloudWatch), retention and alarms are
  part of the AWS stage: HIMS-OPS-004 / HIMS-PLAT-019 (🔒 AWS).
- Browser-side tracing is not used (would risk PHI in client error reports, spec 29.1).

## Alternatives considered
- Vendor agents (Datadog, New Relic): rejected for now; OpenTelemetry keeps the choice open and
  works with AWS X-Ray through the ADOT collector.
- Always-on tracing to the console: rejected; noisy and slower for local work.
