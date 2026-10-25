from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _sync_catalog(sender, **kwargs):
    from .services import sync_permission_catalog, sync_system_roles

    sync_permission_catalog()
    sync_system_roles()


class AccessControlConfig(AppConfig):
    name = "apps.access_control"
    label = "access_control"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        post_migrate.connect(_sync_catalog, sender=self)
