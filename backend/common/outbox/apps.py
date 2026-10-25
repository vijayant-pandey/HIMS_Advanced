from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class OutboxConfig(AppConfig):
    name = "common.outbox"
    label = "outbox"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Each domain registers its event handlers in an ``event_handlers`` module.
        autodiscover_modules("event_handlers")
