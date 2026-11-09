"""Admin console for the compliance registers (HIMS-COMP). Changes go through the same services as
the app, so the rules and audit are identical. Nothing can be deleted."""

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.template.response import TemplateResponse
from django.urls import path

from apps.access_control.catalog import P
from apps.access_control.selectors import has_permission
from common import database_roles
from common.admin.options import ReadOnlyModelAdmin
from common.exceptions import DomainError
from common.security_headers import policy_mode

from . import browser_reports, console_access, incidents, services
from .models import (
    BrowserSecurityReport,
    ComplianceRequirement,
    ConsoleAccessBlock,
    IncidentNotification,
    RiskEntry,
    SecurityIncident,
)


class _ComplianceAdmin(ReadOnlyModelAdmin):
    """Visible to compliance.view; edits need compliance.manage."""

    def has_module_permission(self, request):
        return has_permission(request.user, P.COMPLIANCE_VIEW)

    def has_view_permission(self, request, obj=None):
        return has_permission(request.user, P.COMPLIANCE_VIEW)

    def _can_manage(self, request) -> bool:
        return has_permission(request.user, P.COMPLIANCE_MANAGE)


@admin.register(ComplianceRequirement)
class ComplianceRequirementAdmin(_ComplianceAdmin):
    list_display = ("code", "jurisdiction", "title", "status", "owner", "next_review_on")
    list_filter = ("jurisdiction", "status", "regulation")
    search_fields = ("code", "title", "citation", "owner")
    fields = (
        "code",
        "jurisdiction",
        "regulation",
        "citation",
        "title",
        "summary",
        "hims_support",
        "status",
        "owner",
        "evidence",
        "next_review_on",
        "reviewed_by",
        "reviewed_at",
        "version",
    )
    editable = ("status", "owner", "evidence", "next_review_on")

    def has_change_permission(self, request, obj=None):
        return self._can_manage(request)

    def get_readonly_fields(self, request, obj=None):
        return [name for name in self.fields if name not in self.editable]

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change=change, **kwargs)

        class EvidenceForm(form):
            def clean(self):
                data = super().clean()
                if (
                    data.get("status") == ComplianceRequirement.Status.VERIFIED
                    and not (data.get("evidence") or "").strip()
                ):
                    raise ValidationError("Say where the proof is before marking this verified.")
                return data

        return EvidenceForm

    def save_model(self, request, obj, form, change):
        data = {name: form.cleaned_data[name] for name in self.editable}
        services.update_requirement(
            actor=request.user, requirement_id=obj.pk, version=obj.version, request=request, **data
        )


@admin.register(RiskEntry)
class RiskEntryAdmin(_ComplianceAdmin):
    list_display = (
        "code",
        "title",
        "category",
        "score",
        "treatment",
        "status",
        "owner",
        "review_on",
    )
    list_filter = ("status", "treatment", "category")
    search_fields = ("code", "title", "owner")
    fields = (
        "code",
        "title",
        "description",
        "category",
        "likelihood",
        "impact",
        "treatment",
        "mitigation",
        "status",
        "owner",
        "review_on",
        "acceptance_reason",
        "version",
    )
    readonly_fields = ("code", "version")

    @admin.display(description="Score")
    def score(self, obj):
        return obj.score

    def has_add_permission(self, request, *args):
        return self._can_manage(request)

    def has_change_permission(self, request, obj=None):
        return self._can_manage(request)

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change=change, **kwargs)

        class AcceptanceForm(form):
            def clean(self):
                data = super().clean()
                accepted = (
                    data.get("status") == RiskEntry.Status.ACCEPTED
                    or data.get("treatment") == RiskEntry.Treatment.ACCEPT
                )
                if accepted and not (data.get("acceptance_reason") or "").strip():
                    raise ValidationError("Give the reason for accepting this risk.")
                return data

        return AcceptanceForm

    def save_model(self, request, obj, form, change):
        names = [name for name in self.fields if name not in self.readonly_fields]
        data = {name: form.cleaned_data[name] for name in names}
        if change:
            services.update_risk(
                actor=request.user, risk_id=obj.pk, version=obj.version, request=request, **data
            )
            return
        risk = services.create_risk(actor=request.user, request=request, **data)
        obj.pk = risk.pk
        obj._state.adding = False


class IncidentNotificationInline(admin.TabularInline):
    model = IncidentNotification
    extra = 0
    can_delete = False
    fields = ("kind", "due_at", "status", "done_at", "done_by", "reference", "note")
    readonly_fields = fields

    def has_view_permission(self, request, obj=None):
        return has_permission(request.user, P.COMPLIANCE_VIEW)

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class IncidentAddForm(forms.ModelForm):
    class Meta:
        model = SecurityIncident
        fields = ("title", "description", "severity", "personal_data_affected", "people_affected")


@admin.register(SecurityIncident)
class SecurityIncidentAdmin(_ComplianceAdmin):
    list_display = ("title", "severity", "status", "detected_at", "personal_data_affected")
    list_filter = ("status", "severity", "personal_data_affected")
    search_fields = ("title",)
    inlines = [IncidentNotificationInline]
    editable = (
        "severity",
        "status",
        "occurred_at",
        "personal_data_affected",
        "people_affected",
        "actions_taken",
        "closure_summary",
    )

    def has_add_permission(self, request, *args):
        return self._can_manage(request)

    def has_change_permission(self, request, obj=None):
        return self._can_manage(request)

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            kwargs["form"] = IncidentAddForm
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return list(IncidentAddForm.Meta.fields)
        return ["title", "description", "detected_at", *self.editable, "closed_at", "reported_by"]

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return []
        return ["title", "description", "detected_at", "closed_at", "reported_by"]

    def save_model(self, request, obj, form, change):
        data = form.cleaned_data
        if not change:
            incident = incidents.report_incident(
                actor=request.user,
                request=request,
                title=data["title"],
                description=data["description"],
                severity=data["severity"],
                personal_data_affected=data["personal_data_affected"],
                people_affected=data["people_affected"],
            )
            obj.pk = incident.pk
            obj._state.adding = False
            return
        try:
            incidents.update_incident(
                actor=request.user,
                incident_id=obj.pk,
                version=obj.version,
                request=request,
                **{name: data[name] for name in self.editable},
            )
        except DomainError as exc:
            self.message_user(request, exc.detail, messages.ERROR)
            obj.refresh_from_db()


@admin.register(BrowserSecurityReport)
class BrowserSecurityReportAdmin(_ComplianceAdmin):
    """What browsers blocked; marking one reviewed follows the same rules as the app."""

    list_display = ("day", "directive", "blocked", "page_path", "occurrences", "reviewed_at")
    list_filter = ("directive", "day")
    search_fields = ("blocked", "page_path")
    actions = ["mark_reviewed"]

    @admin.action(description="Mark selected as reviewed")
    def mark_reviewed(self, request, queryset):
        if not self._can_manage(request):
            self.message_user(request, "You may not change these.", messages.ERROR)
            return
        for row in queryset:
            try:
                browser_reports.review_report(
                    actor=request.user,
                    report_id=row.pk,
                    version=row.version,
                    note="Reviewed in the admin console",
                    request=request,
                )
                self.message_user(request, f"{row}: reviewed.")
            except DomainError as exc:
                self.message_user(request, f"{row}: {exc.detail}", messages.ERROR)


@admin.register(ConsoleAccessBlock)
class ConsoleAccessBlockAdmin(_ComplianceAdmin):
    """Addresses the console refused (HIMS-SEC-015). Marking one reviewed follows the same rules as
    the app. Also holds the console's "Security status" page."""

    change_list_template = "admin/compliance/consoleaccessblock/change_list.html"
    list_display = (
        "day",
        "ip_address",
        "attempts",
        "last_path",
        "signed_in_user",
        "last_seen_at",
        "reviewed_at",
    )
    list_filter = ("day",)
    search_fields = ("ip_address", "last_path")
    actions = ["mark_reviewed"]

    @admin.action(description="Mark selected as reviewed")
    def mark_reviewed(self, request, queryset):
        if not self._can_manage(request):
            self.message_user(request, "You may not change these.", messages.ERROR)
            return
        for row in queryset:
            try:
                console_access.review_block(
                    actor=request.user,
                    block_id=row.pk,
                    version=row.version,
                    note="Reviewed in the admin console",
                    request=request,
                )
                self.message_user(request, f"{row}: reviewed.")
            except DomainError as exc:
                self.message_user(request, f"{row}: {exc.detail}", messages.ERROR)

    def get_urls(self):
        return [
            path(
                "security-status/",
                self.admin_site.admin_view(self.security_status_view),
                name="compliance_security_status",
            ),
            *super().get_urls(),
        ]

    def security_status_view(self, request):
        """Browser protection, where the console may be used from, and the database users: the
        same facts as the Compliance page's tabs, read-only (settings change only at hosting)."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        with connection.cursor() as cursor:
            database = database_roles.inspect(cursor)
        context = {
            **self.admin_site.each_context(request),
            "title": "Security status",
            "policy_mode": policy_mode(),
            "trusted_proxies": list(settings.HIMS_TRUSTED_PROXIES),
            "console": console_access.console_status(request),
            "database": database,
            "database_separated": database["set_up"]
            and all(check["passed"] for check in database["checks"]),
            "browser_reports_to_review": BrowserSecurityReport.objects.filter(
                reviewed_at__isnull=True
            ).count(),
        }
        return TemplateResponse(request, "admin/compliance/security_status.html", context)


@admin.register(IncidentNotification)
class IncidentNotificationAdmin(_ComplianceAdmin):
    """Record a notice as done or not required, with the same rules as the app."""

    list_display = ("kind", "incident", "due_at", "status", "done_at", "reference")
    list_filter = ("status", "kind")
    actions = ["mark_done"]

    @admin.action(description="Mark selected as done (notice has been sent)")
    def mark_done(self, request, queryset):
        if not self._can_manage(request):
            self.message_user(request, "You may not change these.", messages.ERROR)
            return
        for row in queryset:
            try:
                incidents.record_notification(
                    actor=request.user,
                    notification_id=row.pk,
                    status=IncidentNotification.Status.DONE,
                    reference="Recorded in the admin console",
                    request=request,
                )
                self.message_user(request, f"{row}: done.")
            except DomainError as exc:
                self.message_user(request, f"{row}: {exc.detail}", messages.ERROR)
