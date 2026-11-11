"""Performance checks in the admin console (HIMS-DATA-002, HIMS-OPS-017).

The results are evidence and read-only (the database refuses changes anyway). People holding
``platform.performance.manage`` get "Run the index check now", the same service the app's
Performance screen uses; it only reads, and it is audited by the service. Response times and the
volume check run from the server command line.
"""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import path
from django.utils.html import format_html, format_html_join

from apps.access_control.catalog import P
from apps.access_control.selectors import has_permission
from common.admin.site import can_use_console
from common.exceptions import ConflictError

from .models import PerformanceCheck
from .services import run_index_check


def _can_view(user) -> bool:
    return can_use_console(user) and has_permission(user, P.PERFORMANCE_VIEW)


def _can_manage(user) -> bool:
    return can_use_console(user) and has_permission(user, P.PERFORMANCE_MANAGE)


@admin.register(PerformanceCheck)
class PerformanceCheckAdmin(admin.ModelAdmin):
    change_list_template = "admin/performance/performancecheck/change_list.html"
    list_display = (
        "finished_at",
        "kind",
        "outcome",
        "summary",
        "trigger",
        "database",
        "dataset_rows",
    )
    list_filter = ("kind", "outcome", "trigger")
    ordering = ("-finished_at",)
    readonly_fields = (
        "kind",
        "outcome",
        "summary",
        "started_at",
        "finished_at",
        "trigger",
        "requested_by_id",
        "database",
        "environment",
        "release",
        "dataset_rows",
        "table_sizes",
        "result_table",
    )
    fields = readonly_fields

    def has_module_permission(self, request):
        return _can_view(request.user)

    def has_view_permission(self, request, obj=None):
        return _can_view(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Rows per table when measured")
    def table_sizes(self, obj):
        return format_html(
            "<ul>{}</ul>",
            format_html_join(
                "", "<li>{}: {}</li>", ((t, f"{n:,}") for t, n in sorted(obj.dataset.items()))
            ),
        )

    @admin.display(description="Results")
    def result_table(self, obj):
        if obj.kind == PerformanceCheck.Kind.INDEXES:
            head = (
                "<tr><th>Result</th><th>Query</th><th>Time</th><th>Indexes used</th>"
                "<th>Note</th></tr>"
            )
            rows = (
                (
                    "Passed" if item.get("passed") else "FAILED",
                    item.get("label", ""),
                    f"{item.get('ms', 0):.1f} ms (budget {item.get('budget_ms', 0):.0f})",
                    ", ".join(item.get("indexes_used") or []) or "none",
                    item.get("detail", ""),
                )
                for item in obj.results
            )
        else:
            head = (
                "<tr><th>Result</th><th>Screen</th><th>p50 / p95</th><th>Queries</th>"
                "<th>Note</th></tr>"
            )
            rows = (
                (
                    "Passed" if item.get("passed") else "FAILED",
                    item.get("label", ""),
                    f"{item.get('p50_ms', 0):.0f} / {item.get('p95_ms', 0):.0f} ms "
                    f"(target {item.get('target_ms', 0):.0f})",
                    str(item.get("queries", "")),
                    item.get("detail", ""),
                )
                for item in obj.results
            )
        return format_html(
            "<table>{}{}</table>",
            format_html(head),
            format_html_join(
                "", "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>", rows
            ),
        )

    def get_urls(self):
        return [
            path(
                "run-index-check/",
                self.admin_site.admin_view(self.run_index_check_view),
                name="performance_run_index_check",
            ),
            *super().get_urls(),
        ]

    def changelist_view(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), "can_manage": _can_manage(request.user)}
        return super().changelist_view(request, extra_context)

    def run_index_check_view(self, request):
        if request.method != "POST" or not _can_manage(request.user):
            raise PermissionDenied
        try:
            check = run_index_check(
                trigger=PerformanceCheck.Trigger.ON_DEMAND, actor=request.user, request=request
            )
        except ConflictError as error:
            messages.error(request, str(error.detail))
            return redirect("admin:performance_performancecheck_changelist")
        if check.outcome == PerformanceCheck.Outcome.PASSED:
            messages.success(request, f"Index check passed: {check.summary}.")
        else:
            messages.error(request, f"Index check failed: {check.summary}.")
        return redirect("admin:performance_performancecheck_change", check.pk)
