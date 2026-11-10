from django.apps import AppConfig
from django.db import connection
from django.db.models.signals import post_migrate


def _sync(sender, **kwargs):
    # post_migrate also fires after partial migrations; sync once the tables exist.
    if "compliance_requirements" not in connection.introspection.table_names():
        return
    from .services import sync_catalog

    sync_catalog()
    if "retention_rules" in connection.introspection.table_names():
        from .retention import sync_rules

        sync_rules()


class ComplianceConfig(AppConfig):
    name = "apps.compliance"
    label = "compliance"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        post_migrate.connect(_sync, sender=self)
