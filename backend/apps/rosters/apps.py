from django.apps import AppConfig
from django.db.models.signals import post_save


def _posting_saved(sender, instance, **kwargs):
    """A posting that ends (in the app or the admin console) cancels that person's shifts in
    that department after its last day."""
    if instance.valid_until is None:
        return
    from .services import cancel_future_shifts

    cancel_future_shifts(
        instance.staff,
        after=instance.valid_until,
        department=instance.department,
        reason="The posting in this department ended",
    )


class RostersConfig(AppConfig):
    name = "apps.rosters"
    label = "rosters"
    verbose_name = "Rotas and leave"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        post_save.connect(
            _posting_saved,
            sender="staff.StaffDepartmentAssignment",
            dispatch_uid="hims.rosters.posting_saved",
        )
