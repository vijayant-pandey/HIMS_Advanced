# Threat model (spec 23; HIMS-COMP-005)

DRAFT for security review. Method: STRIDE over the parts of HIMS built so far. Live risks and
scores: [risk-register.md](risk-register.md) and the Compliance page. Repeat before each phase that
adds patient data, and when hosting is chosen.

## What we protect

| Asset | Why it matters |
|---|---|
| Patient records (from Phase 2) | Most sensitive data; harm if exposed or wrong |
| Staff identities, licences, documents | Personal data; who is allowed to treat |
| Access rights and sessions | The keys to everything else |
| Audit log | The evidence of who did what |
| Encryption and chain keys, database credentials | Their loss defeats other controls |

## How it fits together, and where trust changes

```
Browser ──HTTPS──▶ React app ──/api/v1──▶ Django API ──▶ PostgreSQL (one per hospital)
                                  │  │
Admin console (two-factor) ───────┘  ├──▶ Redis/Celery ──▶ email, SMS providers
                                     └──▶ file storage (permission-checked downloads)
```

Trust boundaries: (1) browser to server: nothing from the browser is trusted, the server checks every
permission; (2) server to database; (3) server to outside providers; (4) one hospital to another:
separate deployments, separate databases; (5) developers and hosting staff to production.

## Threats and what stops them

| Type | Threat | Controls today | Gap (tracked) | Risk |
|---|---|---|---|---|
| **S**poofing | Stolen password or session | Two-factor for privileged roles, throttling keyed on the real address (HIMS-SEC-014), 12+ character passwords, secure cookies, sign-in register, confirm before sensitive actions so a stolen session cannot change access (HIMS-IAM-007), idle sign-out | Two-factor for clinical roles; passkeys; step-up sign-in (HIMS-IAM-007/014) | R-001 |
| **S**poofing | Forged invitation or reset link | Signed single-use expiring tokens, kept out of server logs and the message log | — | R-001 |
| **T**ampering | Altering audit records | Append-only triggers, keyed hash chain, daily check, alerts | External chain copy (HIMS-SEC-016); separate DB roles (HIMS-OPS-007, **done 2026-11-08**: the app's database user cannot TRUNCATE the audit log or touch its triggers) | R-007 |
| **T**ampering | Injection, cross-site scripting, forged requests | ORM queries, React escaping, CSRF tokens, input validation | Content security policy (HIMS-SEC-012) | R-005 |
| **T**ampering | Malicious upload | Type/size checks from file content, no public links, sandboxed responses | Malware scan (HIMS-SEC-013) | R-006 |
| **R**epudiation | "I didn't do that" | Every change audited with who, when, before/after, reference number, real client address believed only from our own proxies (HIMS-SEC-014) | Set `HIMS_TRUSTED_PROXIES` correctly at hosting and check it on the Compliance page | R-007 |
| **I**nformation disclosure | Insider browsing | Least-privilege roles, separation of duties, access reviews | Patient-level rules, chart-read audit, restricted records (Phase 2) | R-003 |
| **I**nformation disclosure | Leak through logs, traces, email | No query strings, no SQL values, hidden tokens, no clinical text in messages; tested | Secret-in-logs test (spec 13.5) | R-009 |
| **I**nformation disclosure | Leak of secrets | Secret scan in CI, gitignored env files, encryption of secrets | Managed secret store at hosting | R-008 |
| **I**nformation disclosure | Another hospital's data | One database per hospital, environment guard | Isolation tests at hosting | R-012 |
| **D**enial of service | Flooding, lost data, ransomware | Rate limits, safe retries | Backups, restore drills, RTO/RPO, WAF at hosting; load tests | R-010 |
| **E**levation of privilege | Acting beyond a role | Default deny on server, escalation guard, no self-granted access, last-admin protection; tested | Independent penetration test | R-004 |
| Supply chain | Poisoned library or action | Hash-locked libraries, SHA-pinned actions, vulnerability scans | SBOM at release | R-011 |
| Clinical safety | Wrong-patient record | Designed: duplicate check, identity header, entered-in-error, two-person merge | Build Phase 2; doctor sign-off | R-014 |

## Before go-live

Independent security review and penetration test · hosting threat review · the go/no-go evidence in
spec 27.5.
