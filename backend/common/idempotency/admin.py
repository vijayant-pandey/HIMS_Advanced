from django.contrib import admin

from common.admin.options import ReadOnlyModelAdmin

from .models import IdempotencyRecord


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(ReadOnlyModelAdmin):
    list_display = ("created_at", "operation", "actor_id", "response_status", "expires_at")
    list_filter = ("operation",)
    search_fields = ("key", "actor_id")
    exclude = ("response_body",)  # may contain record data; not needed for operations
