# The free Development environment on Render + Neon (HIMS-OPS-024)

No payment card anywhere ([ADR-034](../decisions/ADR-034-free-hosting-without-a-card.md)):
**Render** runs HIMS (free web service), **Neon** holds the database (free PostgreSQL),
**cron-job.org** calls HIMS every minute to run the scheduled jobs (and keeps it awake).
Synthetic test data only, never real patients. Why not Northflank: its database asks for a card,
and on 2026-11-11 its status page showed an open security incident.

**Never paste a password, key or connection string into chat, email or Git.** They go into Render's
environment settings and into one file on your PC that Git ignores (`backend\.env.hosted-dev`).

## 1. Neon: the database

1. New project `hims-dev`, Postgres 17, AWS **Asia Pacific 1 (Singapore)**.
2. **Connect** → switch **Connection pooling off** → copy the connection string (no `-pooler` in the
   address) into Notepad. HIMS needs the direct connection: database updates and the scheduled
   jobs' lock do not work through the pooler.
3. If a password was ever shared by mistake: **Roles → neondb_owner → Reset password**, then copy
   the new string.

## 2. Keys for this environment (CMD, on your PC)

```
cd backend
.venv\Scripts\activate.bat
python -c "import secrets; print(secrets.token_urlsafe(50))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print('dev-2026:' + secrets.token_hex(32))"
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

The four lines printed are, in order: the secret key, the encryption key, the audit chain key and
the timer token. Put them in Notepad next to the connection string. They belong to this environment
only; your PC's hospitals keep their own.

## 3. The settings file on your PC: `backend\.env.hosted-dev`

Create it in Notepad (Save as type: All files). Git ignores every `.env.*` file. Replace each
`<...>` with the value from step 1 or 2, and `hims-dev` with your Render name if Render gives a
different one in step 5.

```
HIMS_ENVIRONMENT=development
HIMS_DATABASE_ENVIRONMENT=development
HIMS_DEPLOYMENT_ID=hims-dev-in
DATABASE_URL=<the Neon connection string, pooling off>
DJANGO_SECRET_KEY=<line 1 of step 2>
HIMS_FIELD_ENCRYPTION_KEYS=<line 2>
HIMS_AUDIT_CHAIN_KEYS=<line 3>
HIMS_SCHEDULER_TOKEN=<line 4>
DJANGO_ALLOWED_HOSTS=hims-dev.onrender.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://hims-dev.onrender.com
HIMS_APP_BASE_URL=https://hims-dev.onrender.com
HIMS_TRUSTED_PROXIES=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10
HIMS_ENABLE_ADMIN=false
HIMS_ACCEPT_LOCAL_DOCUMENT_STORAGE=true
HIMS_ACCEPT_UNSCANNED_UPLOADS=true
WEB_CONCURRENCY=2
```

`HIMS_ACCEPT_...` say "test data only": documents are wiped on each deploy and uploads are checked
by the test-file stand-in, not a real virus scanner. The console is off on the internet
(`HIMS_ENABLE_ADMIN=false`); everything is in the screens.

## 4. Create the database tables and the first administrator (CMD, on your PC)

Choose the administrator's password (12 characters or more) and keep it in your password manager.
Use a made-up email: no email is sent from this environment yet (HIMS-OPS-011).

```
cd backend
.venv\Scripts\activate.bat
set HIMS_ENV_FILE=.env.hosted-dev
set DJANGO_SETTINGS_MODULE=config.settings.production
python manage.py migrate
set HIMS_ADMIN_PASSWORD=<the administrator's password>
python manage.py provision_organization --legal-name "HIMS Development (synthetic data)" --display-name "HIMS Dev" --country IN --timezone Asia/Kolkata --currency INR --admin-email admin@hims-dev.test --admin-name "Dev Administrator" --admin-password-env HIMS_ADMIN_PASSWORD
set HIMS_ADMIN_PASSWORD=
set DJANGO_SETTINGS_MODULE=
set HIMS_ENV_FILE=
```

After each later merge that adds migrations, run the same first four lines (up to `migrate`), then
the last two `set ...=` lines, as you do for your PC's hospitals.

## 5. Render: the HIMS service

**New → Web Service → Build and deploy from a Git repository →** the HIMS repository, then:

| Field | Value |
|---|---|
| Name | `hims-dev` (the address becomes `https://hims-dev.onrender.com`; if Render adds letters, use that address in step 3 and here) |
| Region | **Singapore** |
| Branch | `development` |
| Root directory | (empty) |
| Runtime / Language | **Docker** |
| Dockerfile path | `./Dockerfile` |
| Instance type | **Free** |
| Environment variables | Every line of step 3, one by one (name and value) |
| Health check path | Leave empty |
| Auto-deploy | On commit |

**Create Web Service.** The first build takes about 10 minutes (screens, then the server). The log
ends with gunicorn "Booting worker". Open `https://hims-dev.onrender.com`: the sign-in page.

## 6. cron-job.org: the scheduled jobs

Free account at cron-job.org → **Create cronjob**:

| Field | Value |
|---|---|
| Title | HIMS dev scheduled jobs |
| URL | `https://hims-dev.onrender.com/api/v1/scheduled-jobs/run/` |
| Schedule | Every minute |
| Advanced → Request method | **POST** |
| Advanced → Headers | `X-HIMS-Scheduler-Token` = the timer token (line 4 of step 2) |

The first calls may time out while Render wakes up; that is fine. Wrong or missing token: 403 and an
access-denied entry in the audit log.

## 7. Check it

1. Sign in as `admin@hims-dev.test` with the password from step 4; set up two-factor (the role
   requires it), keep the backup codes.
2. **Background jobs → Scheduled jobs**: each job has a last run a minute or less ago.
3. **Compliance → Hosting readiness**: no **Must fix**. "Before real data" items are expected.
4. **Security → My sign-ins**: your own public address is shown, not a `10.x` address. If a private
   address shows, `HIMS_TRUSTED_PROXIES` does not match Render's proxies: tell the developer.
5. On your PC, the same answer from the command line:
   `set HIMS_ENV_FILE=.env.hosted-dev` · `set DJANGO_SETTINGS_MODULE=config.settings.production` ·
   `python manage.py hosting_check` · then clear both settings.

**2026-11-12:** checks 1 to 4 passed on `hims-dev` (13 jobs finished; no "Must fix"; own address
after the Cloudflare note below). HIMS-OPS-024 is done. Every pull request now also runs
`hosting_check` with these settings and throwaway keys (the backend check on GitHub), so a change
that would make this environment "Must fix" fails before it is merged.

## Limits of the free environment

Render sleeps after 15 minutes without visits (the timer keeps it awake; 750 free hours a month
cover one service all month); uploaded documents vanish on each deploy; Neon keeps 6 hours of
restore history; no email or SMS is sent. Fine for testing, never for real patients.

**Note (2026-11-12):** the 750 free hours a month are shared by every free service in the same
Render workspace. With other free services there, the timer keeping HIMS awake every minute can
use them up; run the timer only in working hours, or keep HIMS in a workspace of its own. Behind
Render's proxy the server sees `127.0.0.1`: add `,127.0.0.1` to `HIMS_TRUSTED_PROXIES` (step 3).

**Note (2026-11-12, found in step 7 check 4):** Render also puts **Cloudflare** in front of the
app, so with only the private ranges trusted, **My sign-ins** showed a Cloudflare address
(104.16.x.x to 104.23.x.x) instead of the person's own. Every audit entry, sign-in record and rate
limit would then share one address. Fix (a Render setting, no code change): add Cloudflare's
published ranges (cloudflare.com/ips-v4 and /ips-v6) to the end of `HIMS_TRUSTED_PROXIES`:

```
,173.245.48.0/20,103.21.244.0/22,103.22.200.0/22,103.31.4.0/22,141.101.64.0/18,108.162.192.0/18,190.93.240.0/20,188.114.96.0/20,197.234.240.0/22,198.41.128.0/17,162.158.0.0/15,104.16.0.0/13,104.24.0.0/14,172.64.0.0/13,131.0.72.0/22,2400:cb00::/32,2606:4700::/32,2803:f800::/32,2405:b500::/32,2405:8100::/32,2a06:98c0::/29,2c0f:f248::/32
```

Cloudflare changes this list rarely; check it again before any later hosting work. Fine for the
free test environment. On AWS the load balancer is the only proxy and this list is not used.
