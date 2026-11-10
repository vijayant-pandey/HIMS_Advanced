from django.contrib import admin
from django.http import FileResponse, Http404
from django.urls import path, reverse
from django.utils.html import format_html

from common.admin.options import HimsModelAdmin

from .logo import logo_type
from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(HimsModelAdmin):
    list_display = ("display_name", "legal_name", "country", "default_currency", "status")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "deployment_id",
                    "legal_name",
                    "display_name",
                    "country",
                    "default_timezone",
                    "default_currency",
                    "status",
                    "leave_year_start_month",
                )
            },
        ),
        (
            "Letterhead on printouts and emails",
            {
                "fields": (
                    "logo_preview",
                    "logo",
                    "letterhead_address",
                    "letterhead_phone",
                    "letterhead_email",
                    "letterhead_website",
                    "letterhead_registration",
                    "letterhead_footer",
                )
            },
        ),
        ("Record", {"fields": ("version", "created_at", "updated_at")}),
    )
    # Identity, market and lifecycle are owned by provisioning/the control plane (ADR-009).
    readonly_fields = ("deployment_id", "country", "default_currency", "status", "logo_preview")

    def has_add_permission(self, request, *args):
        return False

    @admin.display(description="Logo now")
    def logo_preview(self, obj):
        if not (obj and obj.logo):
            return "No logo yet."
        return format_html(
            '<img src="{}" alt="Hospital logo" style="max-height:72px;max-width:240px">',
            reverse("admin:organizations_organization_logo"),
        )

    def get_urls(self):
        return [
            path(
                "logo/",
                self.admin_site.admin_view(self.logo_view),
                name="organizations_organization_logo",
            ),
            *super().get_urls(),
        ]

    def logo_view(self, request):
        """Files have no public address, so the console's preview comes through here."""
        organization = Organization.objects.first()
        if organization is None or not organization.logo:
            raise Http404
        try:
            stored = organization.logo.open("rb")
        except OSError:
            raise Http404 from None
        response = FileResponse(stored, content_type=logo_type(stored))
        response["X-Content-Type-Options"] = "nosniff"
        return response
