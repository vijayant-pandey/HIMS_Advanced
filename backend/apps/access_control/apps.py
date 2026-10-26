from django.apps import AppConfig
from django.db import connection
from django.db.models.signals import post_migrate

_REQUIRED_TABLES = {"permissions", "roles", "role_permissions", "organizations"}


def _sync_catalog(sender, **kwargs):
    # post_migrate also fires after partial migrations (e.g. `migrate staff 0002`), when the
    # access-control tables may not exist yet; sync once they do.
    if not set(connection.introspection.table_names()) >= _REQUIRED_TABLES:
        return

    from .services import sync_permission_catalog, sync_system_roles

    sync_permission_catalog()
    sync_system_roles()


class AccessControlConfig(AppConfig):
    name = "apps.access_control"
    label = "access_control"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        post_migrate.connect(_sync_catalog, sender=self)
