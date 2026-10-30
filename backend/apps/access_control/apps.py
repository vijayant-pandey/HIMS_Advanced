from django.apps import AppConfig
from django.db import connection
from django.db.models.signals import post_migrate, post_save

_REQUIRED_TABLES = {"permissions", "roles", "role_permissions", "organizations"}


def _sync_catalog(sender, **kwargs):
    # post_migrate also fires after partial migrations (e.g. `migrate staff 0002`), when the
    # access-control tables may not exist yet; sync once they do.
    if not set(connection.introspection.table_names()) >= _REQUIRED_TABLES:
        return

    from .services import sync_permission_catalog, sync_system_roles

    sync_permission_catalog()
    sync_system_roles()


def _end_cover_when_deactivated(sender, instance, created=False, **kwargs):
    """Switching an account off (leaving, suspension) ends the cover arrangements in which the
    person covers or is covered (HIMS-IAM-017). ``_hims_was_active`` is set by identity's
    pre_save receiver."""
    if created or instance.is_active or not getattr(instance, "_hims_was_active", None):
        return
    from .delegations import end_delegations_for_user

    end_delegations_for_user(instance)


class AccessControlConfig(AppConfig):
    name = "apps.access_control"
    label = "access_control"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from django.conf import settings

        post_migrate.connect(_sync_catalog, sender=self)
        post_save.connect(
            _end_cover_when_deactivated,
            sender=settings.AUTH_USER_MODEL,
            dispatch_uid="hims.access_control.end_cover_when_deactivated",
        )
