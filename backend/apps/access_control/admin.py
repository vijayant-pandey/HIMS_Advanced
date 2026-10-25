from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from common.admin.options import HimsInline, HimsModelAdmin, ReadOnlyModelAdmin
from common.exceptions import DomainError

from .models import Permission, Role, RoleAssignment, RolePermission
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
    list_filter = ("role", ("revoked_at", admin.EmptyFieldListFilter), "facility")
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
