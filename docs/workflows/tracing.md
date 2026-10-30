# Tracing: seeing what one request did (HIMS-PLAT-016)

A **trace** is a timeline of one request: the API call, every database query it ran, tasks it
started and calls to other services, each with how long it took. It answers "why was this screen
slow?" or "what happened for reference number X?". Design: [ADR-021](../decisions/ADR-021-tracing.md).

Tracing is **off** unless you switch it on. Nothing changes for normal use.

## What is never recorded

Search words, query strings, form contents, request or response bodies, passwords, tokens, user
details and SQL values. URLs are kept without the part after `?`. Health checks are skipped.

## Option A: print traces in the launcher window (simplest)

1. Open `backend\.env` (India) or `backend\.env.us` (US) in Notepad.
2. Add a line: `HIMS_TRACING_EXPORTER=console`
3. Restart HIMS (close the launcher window, then `npm run dev` again).
4. Use the app. Each request prints a block of JSON in the backend window, starting with
   `"name": "GET api/v1/..."`. The `hims.request_id` value is the reference number.
5. To switch off: delete the line (or set `none`) and restart.

## Option B: a trace viewer in the browser (needs Docker Desktop)

1. In CMD, in the HIMS folder: `docker compose --profile tracing up -d jaeger`
2. In `backend\.env` add:
   ```
   HIMS_TRACING_EXPORTER=otlp
   OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
   ```
3. Restart HIMS and use the app.
4. Open http://localhost:16686, choose service **hims-api**, press **Find Traces**. Click a
   trace to see each step and its time. To find one request, search for the tag
   `hims.request_id=<reference number>`.
5. Stop the viewer: `docker compose --profile tracing down`

## Finding a trace from a log line

Every JSON log line written during a traced request has `trace_id`. Search for that id in the
trace viewer.

## Hosted environments

| Setting | Development / QA | Staging / Production |
|---|---|---|
| `HIMS_TRACING_EXPORTER` | `otlp` | `otlp` |
| `HIMS_TRACING_SAMPLE_RATIO` | `1.0` | start at `0.2`, adjust for cost |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | the collector next to the app | the collector next to the app |
| `HIMS_RELEASE` | the git commit | the git commit |

On AWS the collector is the AWS Distro for OpenTelemetry (ADOT) sidecar sending to X-Ray /
CloudWatch. That is set up in the AWS stage (HIMS-PLAT-019, 🔒 AWS).

Celery workers trace each task in its worker process. The interim Render hosting can send to any
OTLP-compatible service in the same way.
