# Threat model (spec 23; HIMS-COMP-005, reviewed in HIMS-SEC-011)

**Status:** reviewed 2026-11-11 (internal security review of Phase 1:
[security-review.md](security-review.md)). Method: STRIDE over the parts of HIMS built so far.
Live risks and scores: [risk-register.md](risk-register.md) and the Compliance page. Repeat before
each phase that adds patient data, and when hosting is set up (HIMS-OPS-020). An independent review
and penetration test come before real patient data (HIMS-SEC-021).

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
| **S**poofing | Stolen password or session | Two-factor for privileged roles (passkeys as a phishing-resistant option, HIMS-IAM-014), sign-in limits **per address and per account** (HIMS-SEC-014, HIMS-SEC-011), 12+ character passwords, secure cookies, sign-in register, confirm before sensitive actions so a stolen session cannot change access (HIMS-IAM-007) | Two-factor for clinical roles (Phase 2, D13) | R-001 |
| **S**poofing | Someone uses a screen left open (a ward PC, the bed board on a wall) | Sessions end after 30 minutes without use, which timed screen refreshes do not count as, and after 12 hours in any case; ended sessions audited (HIMS-SEC-011) | — | R-001 |
| **S**poofing | Someone on the internet reaches the admin console, or uses a stolen console session | Console off by default when hosted, two-factor, sign-in lock-out per address and per account, confirm before sensitive actions, and **only listed addresses reach it at all** (HIMS-SEC-015): others get "Not found" before sign-in, a stolen session from elsewhere is refused and named, refusals audited and reviewed | Firewall rule for `/admin/` at hosting (HIMS-OPS-020) | R-001 |
| **S**poofing | Forged invitation or reset link | Signed single-use expiring tokens, kept out of server logs and the message log | — | R-001 |
| **T**ampering | Altering audit records | Append-only triggers, keyed hash chain, daily check, alerts; the app's database user cannot change, delete or empty the audit log or touch its triggers (HIMS-OPS-007) | External chain copy (HIMS-SEC-016) | R-007 |
| **T**ampering | Injection, cross-site scripting, forged requests | ORM queries (no SQL from user input), React escaping, CSRF tokens on every write including the sign-in steps, input validation, content security policy with reports (HIMS-SEC-012); checked in the security review | Independent penetration test (HIMS-SEC-021) | R-005 |
| **T**ampering | Malicious upload | Type/size checks from file content, no public links, sandboxed responses; every upload checked for viruses before it is stored, refused while the scanner is down, refusals audited and reported (HIMS-SEC-013) | ClamAV running at hosting (HIMS-OPS-020) | R-006 |
| **T**ampering | Records deleted too early by the purge, or personal data kept past its purpose | Only six housekeeping kinds can be purged; nothing deleted until a period is set; minimums; shorter periods wait 7 days; legal holds win; confirm it's you; every run recorded append-only and audited (HIMS-COMP-006) | Audit log archive before its purge (HIMS-COMP-007) | R-016 |
| **R**epudiation | "I didn't do that" | Every change audited with who, when, before/after, reference number, real client address believed only from our own proxies (HIMS-SEC-014) | Set `HIMS_TRUSTED_PROXIES` correctly at hosting and check it on the Compliance page | R-007 |
| **R**epudiation | The audit log flooded to hide activity or fill the disk | "No access yet" reports limited to one per person per 10 minutes, none for people with access (HIMS-SEC-011); request rate limits | Disk alarms at hosting (HIMS-OPS-004) | R-007 |
| **I**nformation disclosure | Insider browsing | Least-privilege roles, separation of duties, access reviews | Patient-level rules, chart-read audit, restricted records (Phase 2) | R-003 |
| **I**nformation disclosure | Leak through logs, traces, email | No query strings, no SQL values, hidden tokens, no clinical text in messages; error text in traces filtered with the log rules (HIMS-SEC-020); the secret-in-logs test runs the real flows (HIMS-SEC-019) | — | R-009 |
| **I**nformation disclosure | Leak of secrets | Secret scan in CI, gitignored env files, encrypted secrets; keys rotated with `rotate_encryption_keys` so old keys can be retired (HIMS-SEC-011) | Managed secret store at hosting | R-008 |
| **I**nformation disclosure | Another hospital's data | One database per hospital, environment guard, background events of another hospital refused (HIMS-SEC-011) | Isolation tests at hosting | R-012 |
| **D**enial of service | Flooding, lost data, ransomware | Rate limits, safe retries, backups and restore drills checked against the audit chain (HIMS-OPS-009) | Scheduled backups and cloud restore drill (HIMS-OPS-018), RTO/RPO, WAF at hosting; load test | R-010 |
| **D**enial of service | Screens slow down as records grow until they time out; a check button used to load the database | Busy queries checked against their indexes at hospital size and response times measured against spec 18 targets (`volume_check`, HIMS-DATA-002, HIMS-OPS-017); the audit log's total count capped at 10,000; the index check only reads, needs `platform.performance.manage` and runs one at a time; measuring refused when hosted | Load test with many people at once before go-live (HIMS-OPS-021) | R-010 |
| **E**levation of privilege | Acting beyond a role | Default deny on server, escalation guard, no self-granted access, last-admin protection; every endpoint's access rule read from the code and pinned by tests (HIMS-DOC-001) | Independent penetration test (HIMS-SEC-021) | R-004 |
| Supply chain | Poisoned library or action | Hash-locked libraries, SHA-pinned actions, vulnerability scans (no known issue in shipped packages at the review) | SBOM at release | R-011 |
| Clinical safety | Wrong-patient record | Designed: duplicate check, identity header, entered-in-error, two-person merge | Build Phase 2; doctor sign-off | R-014 |

## Before go-live

Independent security review and penetration test (HIMS-SEC-021) · hosting threat review on Oracle
Cloud (HIMS-OPS-020) · the go/no-go evidence in spec 27.5. The full list is at the end of
[security-review.md](security-review.md).
