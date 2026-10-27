from django.apps import AppConfig
from django.db import connection
from django.db.models.signals import post_migrate

_REQUIRED_TABLES = {"organizations", "feature_flags", "audit_events"}


def _sync_catalog(sender, **kwargs):
    # New features added to catalog.py appear in every hospital (set to "use the default") on
    # the next migrate. Skipped while tables are still missing (partial migrations).
    if not set(connection.introspection.table_names()) >= _REQUIRED_TABLES:
        return

    from apps.organizations.models import Organization

    from .services import ensure_hospital_rows

    for organization in Organization.objects.all():
        ensure_hospital_rows(organization)


class FeaturesConfig(AppConfig):
    name = "apps.features"
    label = "features"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        post_migrate.connect(_sync_catalog, sender=self)
