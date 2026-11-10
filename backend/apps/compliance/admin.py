"""Admin console for the compliance registers (HIMS-COMP). Changes go through the same services as
the app, so the rules and audit are identical. Nothing can be deleted."""

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html_join
from django.utils.http import urlencode

from apps.access_control.catalog import P
from apps.access_control.selectors import has_permission
from apps.compliance.api.scanning_views import scanning_status
from common import database_roles
from common.admin.options import ConfirmIdentityAdminMixin, ReadOnlyModelAdmin
from common.exceptions import DomainError
from common.security_headers import policy_mode

from . import browser_reports, console_access, incidents, retention, services
from .models import (
    BrowserSecurityReport,
    ComplianceRequirement,
    ConsoleAccessBlock,
    IncidentNotification,
    LegalHold,
    RetentionPurgeRun,
    RetentionRule,
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
            "scanning": scanning_status(),
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


# --- Retention and legal hold (HIMS-COMP-006) ---------------------------------------------------


class RetentionRuleForm(forms.ModelForm):
    keep_days = forms.IntegerField(
        required=False,
        min_value=1,
        label="Keep for (days)",
        help_text="Empty = keep for ever (nothing deleted). A shorter period waits "
        f"{retention.SHORTER_PERIOD_WAIT.days} days before it applies; a longer one applies "
        "at once.",
    )
    cancel_pending = forms.BooleanField(
        required=False, label="Cancel the shorter period that is waiting"
    )

    class Meta:
        model = RetentionRule
        fields = ("keep_days",)

    def clean(self):
        data = super().clean()
        kind = retention.CATEGORIES[self.instance.category]
        days = data.get("keep_days")
        if days is not None and not kind.minimum_days <= days <= retention.MAX_DAYS:
            raise ValidationError(
                f"{kind.label}: keep at least {kind.minimum_days} days "
                f"(and at most {retention.MAX_DAYS})."
            )
        if data.get("cancel_pending") and self.instance.pending_from is None:
            raise ValidationError("No shorter period is waiting.")
        return data


@admin.register(RetentionRule)
class RetentionRuleAdmin(ConfirmIdentityAdminMixin, _ComplianceAdmin):
    """How long each kind of housekeeping record is kept. The same rules and audit as the app's
    Retention tab; a change needs "confirm it's you"."""

    form = RetentionRuleForm
    list_display = (
        "kind",
        "keep_days",
        "pending_keep_days",
        "pending_from",
        "would_delete_now",
        "kept_by_hold",
        "updated_by",
    )
    fields = (
        "kind",
        "what",
        "minimum_days",
        "keep_days",
        "pending_keep_days",
        "pending_from",
        "cancel_pending",
        "would_delete_now",
        "kept_by_hold",
        "updated_by",
        "updated_at",
        "version",
    )
    readonly_fields = (
        "kind",
        "what",
        "minimum_days",
        "pending_keep_days",
        "pending_from",
        "would_delete_now",
        "kept_by_hold",
        "updated_by",
        "updated_at",
        "version",
    )

    def has_change_permission(self, request, obj=None):
        return self._can_manage(request)

    @admin.display(description="Kind of record")
    def kind(self, obj):
        return retention.CATEGORIES[obj.category].label

    @admin.display(description="What is deleted")
    def what(self, obj):
        return retention.CATEGORIES[obj.category].what

    @admin.display(description="Minimum (days)")
    def minimum_days(self, obj):
        return retention.CATEGORIES[obj.category].minimum_days

    @admin.display(description="Would delete now")
    def would_delete_now(self, obj):
        plan = retention.preview_one(obj)
        return plan["skipped"] or plan["would_delete"]

    @admin.display(description="Kept by legal hold")
    def kept_by_hold(self, obj):
        return retention.preview_one(obj)["held"]

    def save_model(self, request, obj, form, change):
        stored = RetentionRule.objects.get(pk=obj.pk)
        days = form.cleaned_data["keep_days"]
        if form.cleaned_data["cancel_pending"]:
            days = stored.keep_days
        elif days == stored.keep_days:
            self.message_user(request, "Nothing changed.", messages.INFO)
            return
        try:
            retention.set_period(
                actor=request.user,
                category=obj.category,
                keep_days=days,
                version=stored.version,
                request=request,
            )
        except DomainError as exc:
            self.message_user(request, exc.detail, messages.ERROR)


class LegalHoldAddForm(forms.ModelForm):
    hold_categories = forms.MultipleChoiceField(
        required=False,
        label="Kinds of record held",
        choices=[(key, kind.label) for key, kind in retention.CATEGORIES.items()],
        widget=forms.CheckboxSelectMultiple,
        help_text="None ticked = every kind.",
    )

    class Meta:
        model = LegalHold
        fields = ("reference", "reason", "subject_user")


class LegalHoldReleaseForm(forms.ModelForm):
    release_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Release: why the hold can end",
        help_text="Fill in only to release the hold. The records then follow the normal periods.",
    )

    class Meta:
        model = LegalHold
        fields = ()


@admin.register(LegalHold)
class LegalHoldAdmin(ConfirmIdentityAdminMixin, _ComplianceAdmin):
    """Place a legal hold, or release one with a reason. Never deleted; same rules and audit as
    the app; each needs "confirm it's you"."""

    list_display = ("reference", "held_kinds", "subject_user", "placed_by", "placed_at", "active")
    list_filter = (("released_at", admin.EmptyFieldListFilter),)
    search_fields = ("reference",)
    raw_id_fields = ("subject_user",)
    shown = (
        "reference",
        "reason",
        "held_kinds",
        "subject_user",
        "placed_by",
        "placed_at",
        "released_by",
        "released_at",
    )

    @admin.display(description="Kinds held")
    def held_kinds(self, obj):
        if not obj.categories:
            return "Every kind"
        return ", ".join(
            retention.CATEGORIES[key].label for key in obj.categories if key in retention.CATEGORIES
        )

    @admin.display(boolean=True, description="Active")
    def active(self, obj):
        return obj.is_active

    def has_add_permission(self, request, *args):
        return self._can_manage(request)

    def has_change_permission(self, request, obj=None):
        return self._can_manage(request) and (obj is None or obj.is_active)

    def get_form(self, request, obj=None, change=False, **kwargs):
        kwargs["form"] = LegalHoldAddForm if obj is None else LegalHoldReleaseForm
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ["reference", "reason", "hold_categories", "subject_user"]
        return [*self.shown, "release_reason" if obj.is_active else "release_reason_shown"]

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return []
        return [*self.shown, *([] if obj.is_active else ["release_reason_shown"])]

    @admin.display(description="Why it was released")
    def release_reason_shown(self, obj):
        return obj.release_reason

    def save_model(self, request, obj, form, change):
        data = form.cleaned_data
        try:
            if not change:
                hold = retention.place_hold(
                    actor=request.user,
                    reference=data["reference"],
                    reason=data["reason"],
                    categories=data["hold_categories"],
                    subject_user=data["subject_user"],
                    request=request,
                )
                obj.pk = hold.pk
                obj._state.adding = False
            elif data.get("release_reason", "").strip():
                retention.release_hold(
                    actor=request.user,
                    hold_id=obj.pk,
                    version=obj.version,
                    reason=data["release_reason"],
                    request=request,
                )
            else:
                self.message_user(request, "Nothing changed.", messages.INFO)
        except DomainError as exc:
            self.message_user(request, exc.detail, messages.ERROR)


def _run_summary(key: str, plan: dict) -> tuple[str, str]:
    label = retention.CATEGORIES[key].label if key in retention.CATEGORIES else key
    if plan.get("skipped"):
        return label, plan["skipped"]
    more = " (more next run)" if plan.get("more_left") else ""
    return label, (
        f"deleted {plan.get('deleted', 0)}, kept by legal hold {plan.get('held', 0)}, "
        f"period {plan.get('keep_days')} days{more}"
    )


@admin.register(RetentionPurgeRun)
class RetentionPurgeRunAdmin(_ComplianceAdmin):
    """What each purge run deleted and kept (append-only). Holds "Run the purge now"."""

    change_list_template = "admin/compliance/retentionpurgerun/change_list.html"
    list_display = ("started_at", "trigger", "run_by", "deleted_total", "finished_at")
    list_filter = ("trigger",)
    fields = ("started_at", "finished_at", "trigger", "run_by", "deleted_total", "per_kind")
    readonly_fields = fields

    @admin.display(description="Per kind")
    def per_kind(self, obj):
        return format_html_join(
            "",
            "<p><strong>{}</strong>: {}</p>",
            (_run_summary(key, plan) for key, plan in obj.details.items()),
        )

    def changelist_view(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), "can_manage": self._can_manage(request)}
        return super().changelist_view(request, extra_context)

    def get_urls(self):
        return [
            path(
                "run-now/",
                self.admin_site.admin_view(self.run_now_view),
                name="compliance_retention_run_now",
            ),
            *super().get_urls(),
        ]

    def run_now_view(self, request):
        if request.method != "POST" or not self._can_manage(request):
            raise PermissionDenied
        from apps.identity import confirmation

        back = reverse("admin:compliance_retentionpurgerun_changelist")
        if not confirmation.is_confirmed(request):  # same rule as the API (HIMS-IAM-007)
            messages.warning(request, "Nothing was done yet. Confirm it's you, then try again.")
            return redirect(f"{reverse('admin:confirm_identity')}?{urlencode({'next': back})}")
        try:
            run = retention.run_purge(
                trigger=RetentionPurgeRun.Trigger.MANUAL, actor=request.user, request=request
            )
        except DomainError as exc:
            messages.error(request, exc.detail)
            return redirect(back)
        messages.success(request, f"Purge run: {run.deleted_total} record(s) deleted.")
        return redirect("admin:compliance_retentionpurgerun_change", run.pk)
