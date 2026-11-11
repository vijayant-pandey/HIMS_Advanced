# One server for everything: screens, API, console and scheduled jobs (HIMS-OPS-022, -023)

For hosts with one small service and a timer, such as the free Northflank Sandbox
([ADR-034](../decisions/ADR-034-free-hosting-without-a-card.md),
[hosting analysis](../architecture/hosting/hosting-analysis.md)). Nothing changes on a developer
PC: Vite still serves the screens, and nothing runs on a timer unless you start it.

## The image

`Dockerfile` in the repository root builds the **hosted image**:

1. builds the screens with Node (`npm ci`, `npm run build`, the same steps as CI);
2. installs the server's hash-locked Python packages;
3. puts the built screens in `/app/screens` and sets `HIMS_FRONTEND_DIST=/app/screens`;
4. collects the console and API-docs files.

`backend/Dockerfile` still builds the server alone. CI builds the root image on every pull request
and checks it starts with production settings and holds the screens.

## How one address serves everything (HIMS-OPS-022)

| Address | Answered by |
|---|---|
| `/api/v1/...` | The API, as before |
| `/admin/...` | The console (only if `HIMS_ENABLE_ADMIN` and from allowed addresses) |
| `/health/live/`, `/health/ready/` | Health checks for the host |
| `/static/...` | Console and API-docs files |
| `/assets/...` | The screens' files, fingerprinted, cached for a year |
| Any other address (`/`, `/staff`, `/audit/integrity`) | The app's start page (`index.html`, never cached), so a reload or a bookmark opens the right screen |

The screens get their own protection headers, the same as `frontend/security-headers.json` (a test
keeps them identical), which closes HIMS-SEC-018 for this way of hosting. The sign-in cookie and
CSRF protection work exactly as on a developer PC, because everything is one site.

## Scheduled jobs without an always-on scheduler (HIMS-OPS-023)

HIMS has 13 jobs on a timer ([config/schedule.py](../../backend/config/schedule.py)): sending
waiting background events, sealing the audit log every minute, daily alerts and clean-ups. Where
Celery beat and a worker run, they run them. Where only a timer is available:

```
python manage.py run_scheduled_jobs
```

started **every minute** by the host. Each call:

* runs every job whose time has come, once; the frequent ones (background events, audit sealing)
  run on every call;
* never overlaps another call (a database lock: a second call while one runs does nothing);
* keeps going when one job fails, records the error, tries that job again after 5 minutes, and
  ends with an error so the host marks the run as failed;
* without a broker, handles waiting background events itself instead of publishing them.

Other options: `--list` shows the jobs and their last run; `--only audit-seal-events` runs one job
now. The **Background jobs** page and the console (**Outbox → Scheduled jobs**) show every job, how
often it runs, its last run and its last problem. **Compliance → Hosting readiness** shows "Must
fix" when the audit log is not being sealed, the sign that the timer is not running.

**Hosts without any timer or shell** (Render's free plan): an outside timer such as cron-job.org calls
`POST /api/v1/scheduled-jobs/run/` every minute with the header `X-HIMS-Scheduler-Token` set to
`HIMS_SCHEDULER_TOKEN`. It runs the same due jobs as the command. Off (404) unless the setting is set;
a wrong value gets 403 and is audited; rate limited. Steps: [Render + Neon guide](render-neon-hosting.md).

## On Northflank (not used: its database asks for a card; kept for reference)

The free Development environment runs on Render + Neon instead:
[Render + Neon guide](render-neon-hosting.md).

| Northflank part | Uses |
|---|---|
| Service (deployment from GitHub, branch `development`, Dockerfile at the root) | The web server: the image's default command |
| Scheduled job (cron `* * * * *`, same image) | `python manage.py run_scheduled_jobs` |
| Addon: PostgreSQL | `DATABASE_URL` (with `?sslmode=require` if the addon gives TLS) |
| Release step before the service starts | `python manage.py migrate` |

Then `python manage.py hosting_check` (or the Hosting readiness tab) must show no "Must fix".
