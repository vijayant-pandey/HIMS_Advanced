from django.contrib import admin

from common.admin.site import can_view_audit

from .models import AuditEvent
from .services import AuditAction, record_audit_event


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    """View-only, and only for holders of ``audit.view`` (separation of duties, ADR-013).
    Nobody can add, edit or delete audit events: the database rejects it anyway."""

    list_display = (
        "occurred_at",
        "what",
        "outcome",
        "who",
        "resource_type",
        "resource_id",
        "request_id",
    )
    list_filter = ("outcome", "actor_type", "resource_type")
    search_fields = ("action", "resource_id", "request_id", "actor_id")
    date_hierarchy = "occurred_at"
    ordering = ("-occurred_at",)

    def get_queryset(self, request):
        from .api.views import with_names

        return with_names(super().get_queryset(request))

    @admin.display(description="What happened", ordering="action")
    def what(self, obj):
        from .catalog import label

        return label(obj.action)

    @admin.display(description="Who")
    def who(self, obj):
        return obj.actor_name or obj.actor_type

    def has_module_permission(self, request):
        return can_view_audit(request.user)

    def has_view_permission(self, request, obj=None):
        return can_view_audit(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        if can_view_audit(request.user):
            record_audit_event(
                action=AuditAction.AUDIT_SEARCHED,
                resource_type="audit_event",
                request=request,
                metadata={"via": "admin-console", "query": dict(request.GET.items())},
            )
        return response
