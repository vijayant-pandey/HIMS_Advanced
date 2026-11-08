from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _reapply_database_grants(sender, using="default", **kwargs):
    """After every migrate (run as the owner), give the app's own database user its rights on
    new tables, keep evidence tables append-only for it, and hide new credential columns from the
    read-only user (HIMS-OPS-007). Does nothing until those users have been set up."""
    from django.db import connections

    from common.database_roles import apply_grants

    with connections[using].cursor() as cursor:
        apply_grants(cursor)


class AuditConfig(AppConfig):
    name = "apps.audit"
    label = "audit"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        post_migrate.connect(
            _reapply_database_grants, sender=self, dispatch_uid="hims.database_grants"
        )
