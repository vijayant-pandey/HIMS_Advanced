from django.contrib import admin, messages

from apps.facilities.admin import _LocationAdmin
from common.exceptions import DomainError

from .models import Bed
from .services import change_bed_status


@admin.register(Bed)
class BedAdmin(_LocationAdmin):
    parent_field = "room"
    list_display = ("code", "ward", "room", "bed_type", "status", "status_reason", "is_active")
    list_filter = ("status", "bed_type", "is_active", "facility")
    search_fields = ("code", "ward__code", "room__code")
    fields = (
        "room",
        "code",
        "bed_type",
        "status",
        "status_reason",
        "status_changed_at",
        "is_active",
        "version",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("status", "status_reason", "status_changed_at")
    actions = ["mark_available", "mark_out_of_service"]

    def _change_status(self, request, queryset, status, reason):
        changed = 0
        for bed in queryset:
            try:
                change_bed_status(
                    actor=request.user,
                    bed_id=bed.pk,
                    version=bed.version,
                    status=status,
                    reason=reason,
                    request=request,
                )
                changed += 1
            except DomainError as exc:
                self.message_user(request, f"{bed}: {exc}", messages.WARNING)
        if changed:
            self.message_user(request, f"{changed} bed(s) updated.", messages.SUCCESS)

    @admin.action(description="Mark selected beds available")
    def mark_available(self, request, queryset):
        self._change_status(request, queryset, Bed.Status.AVAILABLE, "")

    @admin.action(description="Mark selected beds out of service")
    def mark_out_of_service(self, request, queryset):
        self._change_status(request, queryset, Bed.Status.OUT_OF_SERVICE, "Set from admin console")
