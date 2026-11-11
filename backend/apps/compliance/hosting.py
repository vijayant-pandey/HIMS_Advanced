"""Hosting readiness: what this server still needs (spec 17, 30, 31, 34; HIMS-OPS-020).

The hosting analysis (docs/architecture/hosting/hosting-analysis.md) lists what any host must give
HIMS. These checks read the running server's own settings and database, so the answer is about
*this* environment, wherever it runs (a free host, a paid one, a developer PC). Each check is:

* ``ok``: met;
* ``fail``: needed before this server is on the internet at all, even with synthetic test data;
* ``warn``: acceptable for a test environment with synthetic data, needed before real patient
  data (a free host usually cannot give it: durable document storage, a virus scanner, backups).

Shown on the Compliance page (Hosting readiness tab) and the console's Security status page;
``python manage.py hosting_check`` prints them and exits 1 when any check fails (``--real-data``:
also when one warns), for deployment pipelines.
"""

from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.utils import timezone

from common.environment import LOCAL_ENVIRONMENTS

OK = "ok"
WARN = "warn"
FAIL = "fail"
STATUSES = (OK, WARN, FAIL)
SEAL_LATE_MINUTES = 10


def _check(key, label, spec, passed, detail, fix, *, before_real_data=False) -> dict:
    return {
        "key": key,
        "label": label,
        "spec": spec,
        "status": OK if passed else (WARN if before_real_data else FAIL),
        "detail": detail,
        "fix": "" if passed else fix,
    }


def _https() -> dict:
    redirect = getattr(settings, "SECURE_SSL_REDIRECT", False)
    secure = getattr(settings, "SESSION_COOKIE_SECURE", False)
    hsts = getattr(settings, "SECURE_HSTS_SECONDS", 0)
    return _check(
        "https",
        "HTTPS only, with secure cookies and HSTS",
        "13.3, 17",
        bool(redirect and secure and hsts),
        f"Redirect to HTTPS: {'on' if redirect else 'off'}; secure cookies: "
        f"{'on' if secure else 'off'}; HSTS: {hsts} s.",
        "Run with the hosted settings (config.settings.production) behind HTTPS.",
    )


def _debug() -> dict:
    return _check(
        "debug",
        "Debug pages off",
        "13.3",
        not settings.DEBUG,
        "Debug pages are on: errors show code and settings."
        if settings.DEBUG
        else "Debug pages are off.",
        "Set DJANGO_DEBUG=false.",
    )


def _hosts() -> dict:
    hosts = list(settings.ALLOWED_HOSTS)
    return _check(
        "allowed_hosts",
        "Only this site's own address is answered",
        "13.3",
        bool(hosts) and "*" not in hosts,
        f"Allowed addresses: {', '.join(hosts) or 'none'}.",
        "Set DJANGO_ALLOWED_HOSTS to the site's address only (never *).",
    )


def _keys() -> dict:
    missing = [
        name
        for name, value in (
            ("HIMS_FIELD_ENCRYPTION_KEYS", settings.HIMS_FIELD_ENCRYPTION_KEYS),
            ("HIMS_AUDIT_CHAIN_KEYS", settings.HIMS_AUDIT_CHAIN_KEYS),
        )
        if not value
    ]
    long_enough = len(settings.SECRET_KEY) >= 50
    if missing:
        detail = "Missing: " + ", ".join(missing) + "."
    else:
        detail = "Set." if long_enough else "DJANGO_SECRET_KEY is shorter than 50 characters."
    return _check(
        "keys",
        "Own keys for this environment",
        "13.3, 30",
        not missing and long_enough,
        detail,
        "Generate keys for this environment and keep them in the host's secret settings.",
    )


def _database() -> list[dict]:
    from common import database_roles

    with connection.cursor() as cursor:
        found = database_roles.inspect(cursor)
    separated = found["set_up"] and all(check["passed"] for check in found["checks"])
    options = connection.settings_dict.get("OPTIONS", {})
    host = connection.settings_dict.get("HOST") or "localhost"
    on_this_machine = host in {"localhost", "127.0.0.1", "::1", "db"}
    encrypted = options.get("sslmode") in {"require", "verify-ca", "verify-full"}
    where = " (database on this machine)." if on_this_machine else "."
    return [
        _check(
            "database_tls",
            "Database connection encrypted",
            "13.3",
            encrypted or on_this_machine,
            f"sslmode={options.get('sslmode') or 'not set'}{where}",
            "Add ?sslmode=require to DATABASE_URL.",
        ),
        _check(
            "database_users",
            "The app runs with its own limited database user",
            "13.2, 17.2",
            separated,
            "Separated." if separated else "Not set up, or a check failed.",
            "Run setup_database_roles with the owner's credentials "
            "(docs/workflows/database-users.md).",
            before_real_data=True,
        ),
    ]


def _scheduled_jobs() -> dict:
    from apps.audit.integrity import unsealed_events

    now = timezone.now()
    # Only events the sealing job looks at (HIMS_AUDIT_SEAL_LOOKBACK_HOURS); older unsealed ones
    # are reported by the integrity check instead.
    late = unsealed_events().filter(
        occurred_at__lt=now - timedelta(minutes=SEAL_LATE_MINUTES),
        occurred_at__gte=now - timedelta(hours=settings.HIMS_AUDIT_SEAL_LOOKBACK_HOURS),
    )
    running = not late.exists()
    return _check(
        "scheduled_jobs",
        "Scheduled jobs are running (audit sealing every minute, daily jobs)",
        "13.4, 14",
        running,
        "The audit log is sealed up to the last few minutes."
        if running
        else f"Audit events older than {SEAL_LATE_MINUTES} minutes are not sealed yet: no "
        "scheduler is running.",
        "Run the scheduler (Celery beat), or the host's cron calling the scheduled jobs "
        "(HIMS-OPS-023).",
    )


def _proxies_and_console() -> list[dict]:
    proxies = list(settings.HIMS_TRUSTED_PROXIES)
    console_on = settings.HIMS_ENABLE_ADMIN
    networks = list(settings.HIMS_ADMIN_ALLOWED_NETWORKS)
    open_to_all = any(network in {"0.0.0.0/0", "::/0"} for network in networks)
    if not console_on:
        console = "Console off."
    else:
        console = f"Console on, allowed from: {', '.join(networks) or 'nowhere'}."
    return [
        _check(
            "trusted_proxies",
            "The host's proxy is named, so client addresses are real",
            "13.1, 13.4",
            bool(proxies),
            f"Trusted proxies: {', '.join(proxies) or 'none'}.",
            "Set HIMS_TRUSTED_PROXIES to the host's load balancer network.",
        ),
        _check(
            "admin_console",
            "Admin console off, or only from allowed addresses",
            "13, ADR-016",
            not console_on or (bool(networks) and not open_to_all),
            console,
            "Set HIMS_ADMIN_ALLOWED_NETWORKS to the office or VPN network.",
        ),
    ]


def _before_real_data() -> list[dict]:
    from apps.recovery.models import Backup

    storage = settings.STORAGES["default"]["BACKEND"]
    email = settings.EMAIL_BACKEND
    cache = settings.CACHES["default"]["BACKEND"]
    latest = Backup.objects.order_by("-created_at").first()
    recent = latest is not None and latest.created_at >= timezone.now() - timedelta(days=1)
    inline = settings.HIMS_OUTBOX_DISPATCH_INLINE
    return [
        _check(
            "documents",
            "Uploaded documents on durable, private storage",
            "4.22, 13.3",
            "FileSystemStorage" not in storage,
            f"Storage: {storage.rsplit('.', 1)[-1]}.",
            "Use S3-compatible storage (HIMS-OPS-015); a free host's disk is wiped on every "
            "deploy.",
            before_real_data=True,
        ),
        _check(
            "virus_scanner",
            "Uploads checked by a real virus scanner",
            "13.3",
            settings.HIMS_VIRUS_SCANNER == "clamd",
            f"Scanner: {settings.HIMS_VIRUS_SCANNER}.",
            "Run ClamAV next to HIMS (HIMS_VIRUS_SCANNER=clamd); it needs about 1 GB of memory.",
            before_real_data=True,
        ),
        _check(
            "email",
            "Emails really sent (invitations, password resets, alerts)",
            "4.23",
            "smtp" in email.lower(),
            f"Email: {email.rsplit('.', 1)[-1]}.",
            "Set EMAIL_BACKEND to SMTP with a provider (HIMS-OPS-011).",
            before_real_data=True,
        ),
        _check(
            "sms",
            "SMS sent through a gateway",
            "4.23",
            "console" not in settings.HIMS_SMS_BACKEND.lower(),
            "SMS are printed on the server console (PO decision 2026-11-08).",
            "Choose an SMS gateway (HIMS-NOTIF-002).",
            before_real_data=True,
        ),
        _check(
            "shared_cache",
            "Rate limits and the sign-in pause shared by every server process",
            "13.1",
            "redis" in cache.lower(),
            f"Cache: {cache.rsplit('.', 1)[-1]} (each server process counts on its own).",
            "Set REDIS_URL.",
            before_real_data=True,
        ),
        _check(
            "background_events",
            "Background events handled by a worker",
            "14.2",
            not inline,
            "Handled in the request after it commits (no broker)."
            if inline
            else "Sent to the broker and handled by the worker.",
            "Set REDIS_URL and run a Celery worker.",
            before_real_data=True,
        ),
        _check(
            "backups",
            "A backup in the last 24 hours",
            "13.3, 17.3, 27",
            recent,
            f"Latest backup: {latest.created_at:%Y-%m-%d %H:%M} UTC."
            if latest
            else "No backup recorded by HIMS.",
            "Schedule backups to off-site storage (the host's backups or HIMS backups).",
            before_real_data=True,
        ),
        _check(
            "api_docs",
            "Interactive API docs off",
            "29",
            not settings.HIMS_ENABLE_API_DOCS,
            "API docs are on." if settings.HIMS_ENABLE_API_DOCS else "API docs are off.",
            "Set HIMS_ENABLE_API_DOCS=false.",
            before_real_data=True,
        ),
    ]


def checks() -> list[dict]:
    return [
        _https(),
        _debug(),
        _hosts(),
        _keys(),
        *_database(),
        _scheduled_jobs(),
        *_proxies_and_console(),
        *_before_real_data(),
    ]


def readiness() -> dict:
    found = checks()
    failing = sum(1 for check in found if check["status"] == FAIL)
    warning = sum(1 for check in found if check["status"] == WARN)
    return {
        "environment": settings.HIMS_ENVIRONMENT,
        "developer_pc": settings.HIMS_ENVIRONMENT in LOCAL_ENVIRONMENTS,
        "ready_to_host": failing == 0,
        "ready_for_real_data": failing == 0 and warning == 0,
        "failing": failing,
        "before_real_data": warning,
        "checks": found,
    }
