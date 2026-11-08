# Runbooks

What to do when something goes wrong in a running HIMS (spec 27.2: each runbook has an owner,
impact assessment, first checks, safe mitigations, escalation, communication plan, recovery
verification and post-incident review criteria).

| Runbook | When |
|---|---|
| [Background jobs (outbox) stuck or failing](outbox-and-background-jobs.md) | Emails not arriving; Background jobs page shows failed or waiting events |
| [Restore a backup / restore drill failed](../workflows/backup-and-restore.md#when-a-drill-fails) | A restore drill failed, or data must be restored |
| [Audit integrity check found a problem](../architecture/data-architecture/audit-integrity.md) | Audit integrity shows problems |
| [Break-glass database access](../workflows/database-users.md#break-glass-emergency-access) | Data must be fixed and the app cannot do it |

More runbooks (database down, high error rate, slow responses, queue backlog after an outage)
come with hosting and alarms (HIMS-OPS-004).
