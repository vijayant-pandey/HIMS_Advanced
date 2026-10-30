from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from apps.organizations.selectors import get_deployment_organization
from common.admin.options import HimsInline, HimsModelAdmin, ReadOnlyModelAdmin
from common.exceptions import DomainError

from . import delegations, reviews
from .models import (
    AccessDelegation,
    AccessReview,
    AccessReviewItem,
    AccessReviewReminder,
    Permission,
    Role,
    RoleAssignment,
    RolePermission,
)
from .selectors import has_permission
from .services import assign_role, revoke_role_assignment, validate_role_assignment


@admin.register(Permission)
class PermissionAdmin(ReadOnlyModelAdmin):
    """The catalog is defined in code (catalog.py) and synced on migrate."""

    list_display = ("codename", "description", "is_active")
    search_fields = ("codename", "description")


class RolePermissionInline(HimsInline):
    model = RolePermission
    fields = ("permission",)
    show_change_link = False

    def _editable(self, obj) -> bool:
        return obj is None or not obj.is_system  # system roles are synced from code

    def has_add_permission(self, request, obj=None):
        return super().has_add_permission(request, obj) and self._editable(obj)

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and self._editable(obj)

    def has_delete_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and self._editable(obj)

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)

        class EscalationGuardForm(formset.form):
            def clean_permission(self):
                permission = self.cleaned_data["permission"]
                if not has_permission(request.user, permission.codename):
                    raise ValidationError(
                        "You cannot put a permission you do not hold organization-wide into a role."
                    )
                return permission

        formset.form = EscalationGuardForm
        return formset


@admin.register(Role)
class RoleAdmin(HimsModelAdmin):
    list_display = ("code", "name", "is_system")
    search_fields = ("code", "name")
    fields = ("organization", "code", "name", "description", "is_system", "created_at")
    readonly_fields = ("is_system",)
    inlines = [RolePermissionInline]


class RoleAssignmentForm(forms.ModelForm):
    class Meta:
        model = RoleAssignment
        fields = ("user", "role", "facility", "department", "valid_until", "reason")

    request = None  # set by RoleAssignmentAdmin.get_form

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        try:
            validate_role_assignment(
                actor=self.request.user,
                user=data["user"],
                role=data["role"],
                facility=data.get("facility"),
                department=data.get("department"),
                valid_until=data.get("valid_until"),
            )
        except DomainError as exc:
            raise ValidationError(str(exc.detail)) from exc
        return data


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(HimsModelAdmin):
    """Grants go through the same service as the API: scope rules, escalation guard, audit."""

    list_display = ("user", "role", "facility", "department", "valid_until", "revoked_at")
    list_filter = (
        "role",
        ("revoked_at", admin.EmptyFieldListFilter),
        ("delegation", admin.EmptyFieldListFilter),
        "facility",
    )
    search_fields = ("user__email", "user__display_name", "role__code")
    autocomplete_fields = ("user",)
    actions = ["revoke_selected"]

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            kwargs["form"] = type(
                "BoundRoleAssignmentForm", (RoleAssignmentForm,), {"request": request}
            )
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return list(RoleAssignmentForm.Meta.fields)
        return [
            "user",
            "role",
            "facility",
            "department",
            "valid_from",
            "valid_until",
            "reason",
            "granted_by",
            "revoked_at",
            "revoked_by",
            "revocation_reason",
            "delegation",
            "delegated_from",
        ]

    def get_readonly_fields(self, request, obj=None):
        return self.get_fields(request, obj) if obj is not None else []

    def save_model(self, request, obj, form, change):
        if change:
            return  # assignments are immutable; revoke and grant again instead
        data = form.cleaned_data
        assignment = assign_role(
            actor=request.user,
            user=data["user"],
            role=data["role"],
            facility=data.get("facility"),
            department=data.get("department"),
            valid_until=data.get("valid_until"),
            reason=data.get("reason", ""),
            request=request,
        )
        obj.pk = assignment.pk
        obj._state.adding = False

    @admin.action(description="Revoke selected role assignments")
    def revoke_selected(self, request, queryset):
        revoked = 0
        for assignment in queryset.filter(revoked_at__isnull=True):
            try:
                revoke_role_assignment(
                    actor=request.user,
                    assignment_id=assignment.pk,
                    reason="Revoked via admin console",
                    request=request,
                )
                revoked += 1
            except DomainError as exc:
                self.message_user(request, f"{assignment}: {exc.detail}", messages.ERROR)
        self.message_user(request, f"Revoked {revoked} assignment(s).")


# --- Access reviews (HIMS-IAM-012) ------------------------------------------------------------
# Same service as the API: snapshot on start, removal revokes the assignment, nobody decides on
# their own access, completion needs every item decided. Nothing here is ever deleted.


@admin.register(AccessReview)
class AccessReviewAdmin(HimsModelAdmin):
    list_display = ("title", "status", "due_on", "created_at", "started_by", "completed_at")
    list_filter = ("status",)
    search_fields = ("title",)
    actions = ["complete_selected", "cancel_selected"]

    def get_fields(self, request, obj=None):
        if obj is None:
            return ["title", "due_on"]
        return [
            "title",
            "status",
            "due_on",
            "created_at",
            "started_by",
            "completed_at",
            "completed_by",
            "notes",
            "decisions",
            "version",
        ]

    def get_readonly_fields(self, request, obj=None):
        return self.get_fields(request, obj) if obj is not None else []

    @admin.display(description="Decisions")
    def decisions(self, obj):
        counts = reviews.summary(obj)
        return (
            f"{counts['pending']} not reviewed, {counts['keep']} kept, "
            f"{counts['remove']} removed, {counts['ended']} already ended"
        )

    def save_model(self, request, obj, form, change):
        if change:
            return  # decisions go through the review items; nothing else changes
        review = reviews.start_review(
            actor=request.user,
            organization=get_deployment_organization(),
            title=form.cleaned_data["title"],
            due_on=form.cleaned_data["due_on"],
            request=request,
        )
        obj.pk = review.pk
        obj._state.adding = False

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change=change, **kwargs)
        if obj is None:

            class StartReviewForm(form):
                def clean(self):
                    data = super().clean()
                    try:
                        reviews.ensure_can_start(due_on=data.get("due_on"))
                    except DomainError as exc:
                        raise ValidationError(str(exc.detail)) from exc
                    return data

            return StartReviewForm
        return form

    @admin.action(description="Complete selected reviews (every item must be decided)")
    def complete_selected(self, request, queryset):
        for review in queryset:
            try:
                reviews.complete_review(
                    actor=request.user,
                    review_id=review.pk,
                    version=review.version,
                    notes="Completed in the admin console",
                    request=request,
                )
                self.message_user(request, f"{review.title}: completed.")
            except DomainError as exc:
                self.message_user(request, f"{review.title}: {exc.detail}", messages.ERROR)

    @admin.action(description="Cancel selected reviews (decisions already made stay)")
    def cancel_selected(self, request, queryset):
        for review in queryset:
            try:
                reviews.cancel_review(
                    actor=request.user,
                    review_id=review.pk,
                    version=review.version,
                    reason="Cancelled in the admin console",
                    request=request,
                )
                self.message_user(request, f"{review.title}: cancelled.")
            except DomainError as exc:
                self.message_user(request, f"{review.title}: {exc.detail}", messages.ERROR)


@admin.register(AccessReviewItem)
class AccessReviewItemAdmin(ReadOnlyModelAdmin):
    """One row per person and role. Decide with the actions (same rules as the app)."""

    list_display = ("person_name", "role_name", "scope", "account_active", "decision", "review")
    list_filter = ("decision", "account_active", "review")
    search_fields = ("person_name", "person_email", "role_name", "scope")
    actions = ["keep_selected", "remove_selected"]

    def _decide(self, request, queryset, decision, comment):
        by_review: dict = {}
        for item in queryset:
            by_review.setdefault(item.review_id, []).append(item.pk)
        for review_id, ids in by_review.items():
            try:
                done = reviews.decide_items(
                    actor=request.user,
                    review_id=review_id,
                    item_ids=ids,
                    decision=decision,
                    comment=comment,
                    request=request,
                )
                self.message_user(request, f"Decided {len(done)} item(s).")
            except (DomainError, ValidationError) as exc:
                detail = getattr(exc, "detail", None) or "; ".join(
                    str(m) for m in getattr(exc, "messages", [exc])
                )
                self.message_user(request, str(detail), messages.ERROR)

    @admin.action(description="Keep selected access")
    def keep_selected(self, request, queryset):
        self._decide(request, queryset, AccessReviewItem.Decision.KEEP, "")

    @admin.action(description="Remove selected access now")
    def remove_selected(self, request, queryset):
        self._decide(
            request,
            queryset,
            AccessReviewItem.Decision.REMOVE,
            "Removed in the admin console during the access review",
        )


@admin.register(AccessReviewReminder)
class AccessReviewReminderAdmin(ReadOnlyModelAdmin):
    list_display = ("kind", "due_on", "recipients", "sent_at")
    list_filter = ("kind",)


# --- Cover arrangements / delegated access (HIMS-IAM-017) ---------------------------------------
# Same service as the API: time limit, reason, no self-granted access, no escalation, auditor
# access never lent, audited. Nothing is deleted; cover is ended early with the action below.


class AccessDelegationForm(forms.ModelForm):
    class Meta:
        model = AccessDelegation
        fields = ("delegator", "delegate", "starts_at", "ends_at", "reason")
        help_texts = {
            "starts_at": "When the cover starts (now or later).",
            "ends_at": "When it ends by itself (at most HIMS_DELEGATION_MAX_DAYS days later).",
        }

    request = None  # set by AccessDelegationAdmin.get_form

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        try:
            delegations.validate_delegation(
                actor=self.request.user,
                delegator=data["delegator"],
                delegate=data["delegate"],
                starts_at=data.get("starts_at"),
                ends_at=data["ends_at"],
                reason=data.get("reason", ""),
            )
        except DomainError as exc:
            raise ValidationError(str(exc.detail)) from exc
        return data


@admin.register(AccessDelegation)
class AccessDelegationAdmin(HimsModelAdmin):
    """Cover arrangements. Adding one lends everything the covered person can lend; use the
    app to choose only some roles."""

    list_display = ("delegate", "delegator", "starts_at", "ends_at", "status_label", "ended_at")
    list_filter = (("ended_at", admin.EmptyFieldListFilter),)
    search_fields = (
        "delegator__email",
        "delegator__display_name",
        "delegate__email",
        "delegate__display_name",
    )
    autocomplete_fields = ("delegator", "delegate")
    actions = ["end_selected"]

    @admin.display(description="Status")
    def status_label(self, obj):
        return AccessDelegation.Status(obj.status).label

    @admin.display(description="Access lent")
    def lent_access(self, obj):
        rows = obj.assignments.select_related("role", "facility", "department")
        lines = [
            f"{a.role.name} ({reviews.scope_label(a)})"
            + (f" - removed: {a.revocation_reason}" if a.revoked_at else "")
            for a in rows
        ]
        return "; ".join(lines) or "-"

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            kwargs["form"] = type(
                "BoundAccessDelegationForm", (AccessDelegationForm,), {"request": request}
            )
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return list(AccessDelegationForm.Meta.fields)
        return [
            "delegator",
            "delegate",
            "starts_at",
            "ends_at",
            "reason",
            "status_label",
            "lent_access",
            "created_by",
            "created_at",
            "ended_at",
            "ended_by",
            "end_reason",
            "version",
        ]

    def get_readonly_fields(self, request, obj=None):
        return self.get_fields(request, obj) if obj is not None else []

    def save_model(self, request, obj, form, change):
        if change:
            return  # end early with the action; arrange a new period instead of editing
        data = form.cleaned_data
        delegation, skipped = delegations.create_delegation(
            actor=request.user,
            delegator=data["delegator"],
            delegate=data["delegate"],
            starts_at=data["starts_at"],
            ends_at=data["ends_at"],
            reason=data["reason"],
            request=request,
        )
        for item in skipped:
            self.message_user(
                request, f"Not lent: {item['role_name']} ({item['scope']}): {item['why']}"
            )
        obj.pk = delegation.pk
        obj._state.adding = False

    @admin.action(description="End selected cover now")
    def end_selected(self, request, queryset):
        for delegation in queryset:
            try:
                delegations.end_delegation(
                    actor=request.user,
                    delegation_id=delegation.pk,
                    version=delegation.version,
                    reason="Ended in the admin console",
                    request=request,
                )
                self.message_user(request, f"{delegation}: ended.")
            except DomainError as exc:
                self.message_user(request, f"{delegation}: {exc.detail}", messages.ERROR)
