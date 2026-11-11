# Hosting analysis: where HIMS can run without a payment card (HIMS-OPS-020)

Spec sections 17 (deployment), 30 (Artifact C: infrastructure and operations), 31 (environments)
and 34 (cost). Decision: [ADR-034](../../decisions/ADR-034-free-hosting-without-a-card.md).
Live check of any server: Compliance page → **Hosting readiness**, or
`python manage.py hosting_check`.

**Checked on 2026-11-11.** Free offers change often: check each provider's sign-up page again on
the day you create the account (links at the end).

**Confirmed at sign-up (2026-11-11):** the PO created a Northflank account on the free Sandbox with
**no card asked**. The free Sandbox offers two regions only: **Europe - West (London)** and
**US - Central (Council Bluffs)**; every other region, including **Asia - South - Delhi**, needs the
paid plan. Chosen: **Europe - West (London)**, the closer of the two to India. GitHub is connected
with access to the HIMS repository only.

## 1. The short answer

* **Oracle Cloud Always Free asks every new account for a credit or debit card** for identity
  checks (it is not charged). Without a card it cannot be used, so ADR-027's plan is on hold.
* **A free host without a card is possible for a test environment with synthetic data**, not for
  real patients. Two plans work:
  1. **Northflank Sandbox** (first choice, if the sign-up really asks for no card): HIMS always on,
     a database, two scheduled jobs.
  2. **Render (free web service) + Neon (free PostgreSQL) + GitHub Actions (scheduled jobs)**: all
     three advertise no card; HIMS sleeps when nobody uses it.
* **Real hospital data needs paid hosting** (backups, a virus scanner, durable document storage,
  agreements such as a HIPAA BAA, and an India region for Indian hospitals). That decision comes
  before go-live, with the PO.

## 2. What HIMS needs from a host

From the specification and from what HIMS runs today. The last column is the readiness check that
proves it on a running server.

| Need | Why (spec) | HIMS today | Check |
|---|---|---|---|
| A Python container, about 512 MB memory | 6.2, 17 | One image for web, worker and scheduler (`backend/Dockerfile`) | — |
| HTTPS, secure cookies, HSTS | 13.3, 17.2 | Hosted settings force them | `https` |
| PostgreSQL 15+, encrypted connection | 9, 13.3 | All data; 1 GB is plenty for a test environment | `database_tls` |
| Separate database users | 13.2, 17.2 | `setup_database_roles` (HIMS-OPS-007) | `database_users` |
| A scheduler: 13 jobs, audit sealing every minute | 13.4, 14 | Celery beat, or an outside clock (HIMS-OPS-023) | `scheduled_jobs` |
| Background events | 14.2 | Celery worker, or handled in the request when there is no broker | `background_events` |
| Redis (broker, shared rate limits) | 14 | Optional: without it, one process works | `shared_cache` |
| Durable private storage for documents | 4.22, 13.3 | Local disk now; S3-compatible later (HIMS-OPS-015) | `documents` |
| Virus scanner (ClamAV, about 1 GB memory) | 13.3 | `test-file` stand-in until hosted (HIMS-SEC-013) | `virus_scanner` |
| Email (SMTP) | 4.23 | Console now (HIMS-OPS-011) | `email` |
| SMS gateway | 4.23 | Printed on the console (PO decision) | `sms` |
| Secrets kept outside the code | 13.3, 31.4 | Environment settings; keys per environment | `keys` |
| Backups and restore drills | 13.3, 17.3, 27 | HIMS backups and drills (HIMS-OPS-009) | `backups` |
| Real client addresses behind the host's proxy | 13.1, 13.4 | `HIMS_TRUSTED_PROXIES` | `trusted_proxies` |
| Admin console only from known addresses | 13, ADR-016 | `HIMS_ADMIN_ALLOWED_NETWORKS` | `admin_console` |
| Separate environments: Development, QA, Staging, Production | 31 | Four branches exist | — |
| India data in India, US data in the US; agreements (BAA, DPA) | 7, 13, 36 | One deployment per hospital and country | — |

## 3. Hosts compared

### Without a payment card

| Host | What is free | Fits HIMS | Limits that matter |
|---|---|---|---|
| **Northflank Sandbox** | 2 always-on services, 2 scheduled jobs, 1 database, no sleeping; **no card asked at sign-up (confirmed 2026-11-11)**; free regions: London and US - Central | Web (Django serving the API, console and screens) + worker; the jobs run the scheduler; PostgreSQL included | Some reports say sign-up still asks for a card to stop abuse; database size and regions not published for the free plan |
| **Render free web service** | Web service, 750 hours a month, sleeps after 15 minutes without visits (about a minute to wake); no card for free services | Django serving everything; events handled in the request | No free worker or cron; the disk is wiped on every deploy; free PostgreSQL is **deleted after 30 days**, so use Neon instead |
| **Neon free PostgreSQL** | 1 GB per project, 100 compute hours a month, restore to any point in the last 6 hours; Singapore region | The database for either plan | Sleeps after 5 minutes idle (wakes in about a second); no India region |
| **GitHub Actions scheduled workflow** | Free with the repository (2,000 minutes a month for private repositories) | Runs the scheduled jobs every 5 minutes against the database | Every 5 minutes at best, sometimes late; audit sealing every 5 minutes instead of every minute |
| **Your own PC + Cloudflare quick tunnel** | `trycloudflare.com` address for a local server, no account | Short demos to someone outside your network | The PC must stay on; the address changes on each start; not for testers over days |
| **Static site hosts** (Cloudflare Pages, Netlify, Vercel, Render static) | The built screens | Not needed: HIMS signs in with cookies, so the screens should come from the same address as the API (HIMS-OPS-022) | A separate address would break sign-in |

### Need a card (even when not charged)

| Host | Why not now |
|---|---|
| Oracle Cloud Always Free | Card required for identity checks; the best free resources (4 ARM cores, 24 GB memory) once a card is available |
| AWS, Google Cloud, Azure free tiers | Card required; the spec's reference design is AWS (section 17) |
| Koyeb, Fly.io | Card required for new accounts since 2026 (Fly.io: a short trial only) |
| Railway | One-time trial credit, then about $1 of credit a month: not enough to keep HIMS running |

## 4. Recommendation: a free Development environment for testing

**Purpose:** the Development environment of spec 31.1 (merged work, synthetic data only), so the PO
and testers can use HIMS from any browser. **No real patient data**, ever, on these hosts: there is
no business associate agreement, no data processing agreement, no India region, no virus scanner and
no durable document storage.

| Part | Plan 1 (Northflank) | Plan 2 (no card for sure) |
|---|---|---|
| Web: API, admin console, screens | Northflank service 1 | Render free web service |
| Database | Northflank PostgreSQL (or Neon) | Neon free, Singapore |
| Scheduled jobs | A Northflank scheduled job (how often it may run: check at sign-up) | GitHub Actions every 5 minutes (also keeps Render awake: about 730 hours a month, inside the 750) |
| Background events | Celery worker as service 2, or in the request | In the request (no broker) |
| Documents | Local disk, accepted for test data (wiped on deploy) | Same |
| Virus scanner | `test-file` stand-in, accepted for test data | Same |
| Email | Free SMTP account (to choose, HIMS-OPS-011) or the log | Same |
| Secrets | The host's secret settings | Render environment settings; GitHub Actions secrets for the jobs |

On either plan, `hosting_check` must show **no "Must fix"** before the first tester signs in, and
it lists what stays "Before real data".

## 5. Environments and branches (spec 31, 32)

The free hosts have room for **one** hosted environment. So:

| Branch | Environment | When |
|---|---|---|
| `development` | **Development** on the free host, deployed automatically after each merge | First (HIMS-OPS-024) |
| `qa` | QA | When paid hosting is chosen; promoted from `development` by a PR |
| `staging` | Staging (production-like) | Same |
| `production` | Production for a real hospital | After the go-live checks (penetration test HIMS-SEC-021, agreements, backups) |

Keep merging feature PRs into `development` as today. Nothing is deployed from `qa`, `staging` or
`production` until those environments exist.

## 6. What must be built before the first deployment

New tickets (in the [backlog](../../backlog/phase-1-foundation.md) and the hosting stage of the
[roadmap](../../status/roadmap.md)):

| Ticket | What | Why |
|---|---|---|
| HIMS-OPS-022 (done) | Serve the screens from the same server as the API (the built React app through WhiteNoise, with the screens' security headers) | One free service; sign-in cookies need one address; also sends the screens' headers (most of HIMS-SEC-018) |
| HIMS-OPS-023 (done) | Scheduled jobs without a worker: a command that runs every due job once, safe to start from an outside clock | Free hosts have no always-on scheduler; the audit log must still be sealed |
| HIMS-OPS-024 | The first free Development environment: account, settings, deploy from `development`, `hosting_check` in the pipeline, the PO's sign-in | The goal of this stage |

The existing hosting-stage tickets keep their purpose and move to whichever host is chosen for real
data: infrastructure as code (HIMS-OPS-003), alarms (HIMS-OPS-004), the deploy pipeline
(HIMS-OPS-005), the migration job (HIMS-OPS-006), email (HIMS-OPS-011), document storage
(HIMS-OPS-015), cloud restore drill (HIMS-OPS-018), database activity logging (HIMS-OPS-019), load
test (HIMS-OPS-021), traces (HIMS-PLAT-019), audit chain copy (HIMS-SEC-016), screens' headers
(HIMS-SEC-018), audit archive (HIMS-COMP-007), penetration test (HIMS-SEC-021).

## 7. Spec sections mapped

| Spec | Says | Free test stage | Before real data |
|---|---|---|---|
| 17.1 Components (ECS, RDS, ElastiCache, S3, KMS) | AWS services | Container host + managed PostgreSQL; no Redis; local disk | A host with the same parts (any cloud), chosen with the PO |
| 17.2 Network and security | Private subnets, WAF, TLS | TLS by the host; app-level console allow-list | Network rules for `/admin/`, WAF |
| 17.3 Backups and recovery | PITR, restore drills | Neon: 6 hours of restore; HIMS backups by hand | Scheduled off-site backups, cloud restore drill |
| 30 Artifact C | Infrastructure as code, accounts, secrets, monitoring | Host settings documented here; secrets in the host | Infrastructure as code for the chosen host |
| 31 Environments | Development, QA, Staging, Production | Development only | All four |
| 34 Cost | No AWS needed to start | No spend | First costs: a small server or two, storage, email, a domain |

## 8. Sources (checked 2026-11-11)

* Render free instances: <https://render.com/docs/free>
* Neon plans: <https://neon.com/docs/introduction/plans>; regions:
  <https://neon.com/docs/introduction/regions>
* Northflank pricing (Sandbox, "No card needed"): <https://northflank.com/pricing>
* Oracle free tier FAQ (card for identity checks): <https://www.oracle.com/cloud/free/faq/>
* GitHub Actions billing and limits: <https://docs.github.com/en/actions/reference/usage-limits-billing-and-administration>
* Cloudflare quick tunnels: <https://blog.cloudflare.com/quick-tunnels-anytime-anywhere/>
* Overviews used to cross-check (third party): <https://render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026>,
  <https://snapdeploy.dev/blog/free-cloud-deployment-platforms-2026-comparison>
