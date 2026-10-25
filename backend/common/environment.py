"""Startup guard against dangerous environment/configuration combinations (spec 31.4).

The guard runs while settings load, before any request or task is served. It refuses to
start rather than risk, for example, a developer workstation writing to a managed database.
"""

from django.core.exceptions import ImproperlyConfigured

LOCAL_ENVIRONMENTS = frozenset({"local", "test"})
MANAGED_ENVIRONMENTS = frozenset({"development", "qa", "staging", "production"})
ALL_ENVIRONMENTS = LOCAL_ENVIRONMENTS | MANAGED_ENVIRONMENTS

# Database hosts a local/test process is allowed to talk to. Anything else is treated as a
# managed database and refused.
LOCAL_DATABASE_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1", "postgres", "db"})

# Which settings module may be combined with which environment.
SETTINGS_PROFILE_ENVIRONMENTS = {
    "local": frozenset({"local"}),
    "test": frozenset({"test"}),
    "production": MANAGED_ENVIRONMENTS,
}


def validate_environment(
    *,
    settings_profile: str,
    environment: str,
    deployment_id: str,
    database_host: str,
    database_environment: str | None,
    debug: bool,
) -> None:
    if environment not in ALL_ENVIRONMENTS:
        raise ImproperlyConfigured(
            f"HIMS_ENVIRONMENT={environment!r} is not one of {sorted(ALL_ENVIRONMENTS)}."
        )

    allowed = SETTINGS_PROFILE_ENVIRONMENTS[settings_profile]
    if environment not in allowed:
        raise ImproperlyConfigured(
            f"Settings profile {settings_profile!r} cannot run with "
            f"HIMS_ENVIRONMENT={environment!r}."
        )

    if not deployment_id:
        raise ImproperlyConfigured("HIMS_DEPLOYMENT_ID must identify this customer deployment.")

    if environment in LOCAL_ENVIRONMENTS:
        if database_host not in LOCAL_DATABASE_HOSTS:
            raise ImproperlyConfigured(
                f"A {environment} process may only use a local database; "
                f"refusing database host {database_host!r}."
            )
        return

    # Managed environments: the database secret carries the environment it belongs to, so a
    # staging process can never be pointed at a production database by a configuration slip.
    if database_environment != environment:
        raise ImproperlyConfigured(
            "HIMS_DATABASE_ENVIRONMENT must match HIMS_ENVIRONMENT "
            f"({database_environment!r} != {environment!r})."
        )
    if debug:
        raise ImproperlyConfigured("DEBUG must be disabled in managed environments.")
