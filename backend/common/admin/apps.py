from django.contrib.admin.apps import AdminConfig


class HimsAdminConfig(AdminConfig):
    """Replaces Django's default admin site with the RBAC-gated, audited HIMS site (ADR-016)."""

    default_site = "common.admin.site.HimsAdminSite"
