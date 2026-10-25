## Ticket

Closes #<!-- issue number --> <!-- every PR links to at least one ticket (spec 32.5) -->

## What and why

## Review checklist

- [ ] Acceptance criteria met; tests added/updated (unit, API, permission/isolation)
- [ ] Database migrations reviewed (expand-and-contract; no irreversible data rewrite without a recovery plan)
- [ ] API contract regenerated (`docs/api/openapi.yaml`, `frontend/src/api/schema.d.ts`) if the API changed
- [ ] Permissions enforced in the backend; new endpoints declare `required_permissions`
- [ ] Audit events recorded for sensitive reads/writes
- [ ] Idempotency / concurrency / retry behaviour covered where required
- [ ] No secrets, real patient data or real clinical documents committed
- [ ] Clinical / finance / security approval obtained if this change needs it

## Risk and rollback

<!-- Clinical, privacy, financial, operational risk. Is application rollback safe with the schema change? -->
