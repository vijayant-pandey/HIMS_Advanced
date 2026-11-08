from django.apps import AppConfig


class RecoveryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.recovery"
    label = "recovery"
    verbose_name = "Backups and restore drills"
