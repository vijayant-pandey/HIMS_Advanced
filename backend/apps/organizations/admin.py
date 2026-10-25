from django.contrib import admin

from common.admin.options import HimsModelAdmin

from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(HimsModelAdmin):
    list_display = ("display_name", "legal_name", "country", "default_currency", "status")
    fields = (
        "deployment_id",
        "legal_name",
        "display_name",
        "country",
        "default_timezone",
        "default_currency",
        "status",
        "version",
        "created_at",
        "updated_at",
    )
    # Identity, market and lifecycle are owned by provisioning/the control plane (ADR-009).
    readonly_fields = ("deployment_id", "country", "default_currency", "status")

    def has_add_permission(self, request, *args):
        return False
