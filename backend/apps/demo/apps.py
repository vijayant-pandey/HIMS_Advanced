from django.apps import AppConfig


class DemoConfig(AppConfig):
    """Demo hospitals with synthetic data for the developer PC (HIMS-QA-004). No tables."""

    name = "apps.demo"
    label = "demo"
    default_auto_field = "django.db.models.BigAutoField"
