from django.apps import AppConfig


class IdempotencyConfig(AppConfig):
    name = "common.idempotency"
    label = "idempotency"
    default_auto_field = "django.db.models.BigAutoField"
