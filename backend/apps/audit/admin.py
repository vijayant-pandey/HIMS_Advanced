from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join

from common.admin.site import can_view_audit
from common.exceptions import ConflictError

from .models import AuditChainEntry, AuditEvent, AuditIntegrityCheck
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


class _AuditorOnlyReadAdmin(admin.ModelAdmin):
    """Read-only, and only for holders of ``audit.view`` (separation of duties)."""

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


@admin.register(AuditChainEntry)
class AuditChainEntryAdmin(_AuditorOnlyReadAdmin):
    """The tamper-evident chain (HIMS-SEC-010). Links hold fingerprints only, no event content.
    The database rejects any change."""

    list_display = ("sequence", "sealed_at", "event_link", "key_id", "short_hash")
    search_fields = ("=event__id", "entry_hash")
    ordering = ("-sequence",)
    readonly_fields = (
        "sequence",
        "event_link",
        "event_hash",
        "previous_hash",
        "entry_hash",
        "key_id",
        "sealed_at",
    )
    fields = readonly_fields

    @admin.display(description="Audit event")
    def event_link(self, obj):
        url = reverse("admin:audit_auditevent_change", args=[obj.event_id])
        return format_html('<a href="{}">{}</a>', url, obj.event_id)

    @admin.display(description="Link fingerprint")
    def short_hash(self, obj):
        return f"{obj.entry_hash[:16]}..."


@admin.register(AuditIntegrityCheck)
class AuditIntegrityCheckAdmin(_AuditorOnlyReadAdmin):
    """Results of the integrity check, and a button to run one now (HIMS-SEC-010)."""

    change_list_template = "admin/audit/auditintegritycheck/change_list.html"
    list_display = (
        "finished_at",
        "outcome",
        "trigger",
        "entries_checked",
        "problem_count",
        "unsealed_overdue",
        "short_head",
    )
    list_filter = ("outcome", "trigger")
    ordering = ("-finished_at",)
    readonly_fields = (
        "outcome",
        "started_at",
        "finished_at",
        "trigger",
        "requested_by_id",
        "events_sealed",
        "entries_checked",
        "last_sequence",
        "chain_head",
        "problem_count",
        "unsealed_overdue",
        "problem_list",
    )
    fields = readonly_fields

    @admin.display(description="Chain head")
    def short_head(self, obj):
        return f"{obj.chain_head[:16]}..." if obj.chain_head else "-"

    @admin.display(description="Problems (first 100)")
    def problem_list(self, obj):
        if not obj.problems:
            return "None"
        return format_html(
            "<ul>{}</ul>",
            format_html_join(
                "",
                "<li><b>{}</b> {}: {}</li>",
                (
                    (
                        p.get("kind", ""),
                        p.get("sequence") or p.get("event_id") or "",
                        p.get("text", ""),
                    )
                    for p in obj.problems
                ),
            ),
        )

    def get_urls(self):
        run = path(
            "run-check/",
            self.admin_site.admin_view(self.run_check_view),
            name="audit_auditintegritycheck_run",
        )
        return [run, *super().get_urls()]

    def run_check_view(self, request):
        from .integrity import run_integrity_check

        if request.method != "POST" or not can_view_audit(request.user):
            raise PermissionDenied
        try:
            check = run_integrity_check(
                trigger=AuditIntegrityCheck.Trigger.ON_DEMAND, actor=request.user, request=request
            )
        except ConflictError as error:
            messages.error(request, error.detail)
            return redirect("admin:audit_auditintegritycheck_changelist")
        if check.outcome == AuditIntegrityCheck.Outcome.PASSED:
            messages.success(
                request, f"Passed: {check.entries_checked} link(s) checked, nothing was changed."
            )
        else:
            messages.error(
                request,
                f"{check.problem_count} problem(s) found. Auditors have been emailed. "
                "Treat this as a possible security incident.",
            )
        return redirect("admin:audit_auditintegritycheck_change", check.pk)
