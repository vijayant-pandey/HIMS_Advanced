"""Backups and restore drills in the admin console (HIMS-OPS-009).

The evidence is read-only (the database refuses changes anyway). People holding
``recovery.manage`` get two buttons: "Make a backup now" (after "confirm it's you", because a
backup is a full copy of every record) and, on a backup, "Run a restore drill". Both are audited
by the service that does the work.
"""

from urllib.parse import urlencode

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join

from apps.access_control.catalog import P
from apps.access_control.selectors import has_permission
from common.admin.site import can_use_console

from .models import Backup, RestoreDrill
from .pg_tools import RecoveryError
from .services import create_backup, run_restore_drill


def _can_view(user) -> bool:
    return can_use_console(user) and has_permission(user, P.RECOVERY_VIEW)


def _can_manage(user) -> bool:
    return can_use_console(user) and has_permission(user, P.RECOVERY_MANAGE)


class _EvidenceAdmin(admin.ModelAdmin):
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


@admin.register(Backup)
class BackupAdmin(_EvidenceAdmin):
    change_list_template = "admin/recovery/backup/change_list.html"
    change_form_template = "admin/recovery/backup/change_form.html"
    list_display = ("created_at", "name", "tables", "rows", "documents", "size", "seconds")
    ordering = ("-created_at",)
    readonly_fields = (
        "name",
        "created_at",
        "created_by_id",
        "database_name",
        "environment",
        "release",
        "dump_bytes",
        "dump_sha256",
        "tables",
        "rows",
        "documents",
        "documents_bytes",
        "seconds",
    )
    fields = readonly_fields

    @admin.display(description="Size (database + documents)")
    def size(self, obj):
        return f"{(obj.dump_bytes + obj.documents_bytes) / 1024 / 1024:.1f} MB"

    def get_urls(self):
        return [
            path(
                "make-backup/",
                self.admin_site.admin_view(self.make_backup_view),
                name="recovery_backup_make",
            ),
            path(
                "<uuid:backup_id>/run-drill/",
                self.admin_site.admin_view(self.run_drill_view),
                name="recovery_backup_run_drill",
            ),
            *super().get_urls(),
        ]

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = {**(extra_context or {}), "can_manage": _can_manage(request.user)}
        return super().changeform_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), "can_manage": _can_manage(request.user)}
        return super().changelist_view(request, extra_context)

    def make_backup_view(self, request):
        if request.method != "POST" or not _can_manage(request.user):
            raise PermissionDenied
        from apps.identity import confirmation

        if not confirmation.is_confirmed(request):  # same rule as the API (HIMS-IAM-007)
            messages.warning(request, "Nothing was done yet. Confirm it's you, then try again.")
            back = urlencode({"next": reverse("admin:recovery_backup_changelist")})
            return redirect(f"{reverse('admin:confirm_identity')}?{back}")
        try:
            backup = create_backup(actor=request.user, request=request)
        except RecoveryError as error:
            messages.error(request, error.detail)
            return redirect("admin:recovery_backup_changelist")
        messages.success(request, f"Backup {backup.name} made. Now run a restore drill on it.")
        return redirect("admin:recovery_backup_change", backup.pk)

    def run_drill_view(self, request, backup_id):
        if request.method != "POST" or not _can_manage(request.user):
            raise PermissionDenied
        backup = get_object_or_404(Backup, pk=backup_id)
        try:
            drill = run_restore_drill(
                backup=backup,
                trigger=RestoreDrill.Trigger.ON_DEMAND,
                actor=request.user,
                request=request,
            )
        except RecoveryError as error:
            messages.error(request, error.detail)
            return redirect("admin:recovery_backup_change", backup.pk)
        if drill.outcome == RestoreDrill.Outcome.PASSED:
            messages.success(request, "Restore drill passed: everything came back.")
        else:
            messages.error(request, f"Restore drill failed: {drill.problem_count} check(s) failed.")
        return redirect("admin:recovery_restoredrill_change", drill.pk)


@admin.register(RestoreDrill)
class RestoreDrillAdmin(_EvidenceAdmin):
    list_display = (
        "finished_at",
        "outcome",
        "backup",
        "trigger",
        "restore_seconds",
        "backup_age_minutes",
        "problem_count",
    )
    list_filter = ("outcome", "trigger")
    ordering = ("-finished_at",)
    readonly_fields = (
        "outcome",
        "backup",
        "started_at",
        "finished_at",
        "trigger",
        "requested_by_id",
        "restore_seconds",
        "backup_age_minutes",
        "restored_database",
        "problem_count",
        "check_list",
    )
    fields = readonly_fields

    @admin.display(description="Checks")
    def check_list(self, obj):
        return format_html(
            "<ul>{}</ul>",
            format_html_join(
                "",
                "<li><b>{}</b> {}{}</li>",
                (
                    (
                        "Passed" if check.get("passed") else "FAILED",
                        check.get("label", ""),
                        f": {check['detail']}" if check.get("detail") else "",
                    )
                    for check in obj.checks
                ),
            ),
        )
