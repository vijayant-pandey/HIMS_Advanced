from django.apps import AppConfig
from django.db.models.signals import post_save


def _posting_saved(sender, instance, **kwargs):
    """A posting that ends (in the app or the admin console) ends that doctor's OPD sessions in
    that department on its last day, and cancels extra sessions after it."""
    if instance.valid_until is None:
        return
    from .services import end_sessions_after

    end_sessions_after(
        instance.staff,
        after=instance.valid_until,
        department=instance.department,
        reason="The posting in this department ended",
    )


class SchedulingConfig(AppConfig):
    name = "apps.scheduling"
    label = "scheduling"
    verbose_name = "Doctor schedules (OPD)"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        post_save.connect(
            _posting_saved,
            sender="staff.StaffDepartmentAssignment",
            dispatch_uid="hims.scheduling.posting_saved",
        )
