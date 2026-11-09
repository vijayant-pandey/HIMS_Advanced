# ADR-027: Host on Oracle Cloud (free offering) at the end of the build, instead of AWS

**Status:** Proposed (PO direction, 2026-11-08) · **Analysis:** HIMS-OPS-020 · **Spec:** 6, 17, 30,
31, 33, 34 · **Log:** [decisions log](../status/decisions-log.md)

## Context

The specification designs the hosted platform on AWS (sections 17 and 30: ECS, RDS PostgreSQL,
ElastiCache Redis, S3 with KMS, Secrets Manager, CloudWatch, WAF). The PO has decided not to use
AWS for now: HIMS will be deployed at the very end of the build on Oracle Cloud's free offering.
The specification is not changed; this ADR records the difference.

## Decision

1. Keep building the application cloud-neutral: PostgreSQL, Redis-compatible broker, S3-compatible
   object storage, environment variables for secrets, OpenTelemetry for traces, containers.
2. Before deploying, run an analysis (HIMS-OPS-020) that maps every hosting requirement of the
   specification to what Oracle Cloud offers, with what is free and what is not, and the gaps.
3. Items labelled "AWS" in the tracker and roadmap become the **hosting stage**: they are done on
   the chosen platform after the analysis, at the end.

## What the analysis must answer (from the specification)

| Requirement (spec) | Question for Oracle Cloud |
|---|---|
| PostgreSQL with backups and point-in-time recovery, separate users (17.1, 17.3, 30.5) | Managed PostgreSQL, or PostgreSQL on a virtual machine with our own backups? Which is in the free offering? |
| Container runtime, a migration job, separate worker and scheduler (17.1, 30.5, 33) | Virtual machine with Docker Compose, or a container service? |
| Redis for the Celery broker and cache (14) | Self-run Redis on the same machine? |
| Object storage with versioning and encryption for documents (6, 30.6) | Oracle Object Storage (S3-compatible API) limits and versioning |
| Secrets and key management (13.3, 30) | Vault service, or environment files on the server? |
| TLS, firewall, admin console allow-list (13.1, 17.2) | Load balancer and certificates; network rules (the app's own allow-list is done, HIMS-SEC-015: [console allow-list](../workflows/console-allow-list.md); the network rule for `/admin/` is the hosting layer) |
| Logs, metrics, traces and alarms (18, 27.2) | Monitoring and logging service; OpenTelemetry export |
| Separate Development, QA, Staging, Production (31) | How many environments fit in the free offering? |
| India and US as separate deployments, data residency (7, 36) | Regions available for each country |
| Cost (34) | What stays free, and the first cost when it grows |

## Consequences

- AWS-specific tickets (Terraform modules for AWS, S3 Object Lock for the audit chain head, AWS
  trace export) are re-planned for Oracle Cloud after the analysis; their purpose stays.
- Free offerings have limits (size, availability); the analysis states whether they suit a pilot
  with real patients or only demos and testing.
