from django.apps import AppConfig
from django.db import connection
from django.db.models.signals import post_migrate

_REQUIRED_TABLES = {"organizations", "numbering_schemes", "audit_events"}


def _create_default_schemes(sender, **kwargs):
    # Hospitals provisioned before numbering existed get the country defaults on their next
    # migrate. Skipped while tables are still missing (partial migrations).
    if not set(connection.introspection.table_names()) >= _REQUIRED_TABLES:
        return

    from apps.organizations.models import Organization

    from .services import ensure_default_schemes

    for organization in Organization.objects.all():
        ensure_default_schemes(organization)


class NumberingConfig(AppConfig):
    name = "apps.numbering"
    label = "numbering"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        post_migrate.connect(_create_default_schemes, sender=self)
