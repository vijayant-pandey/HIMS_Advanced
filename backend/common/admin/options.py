"""Base ModelAdmin classes for the HIMS console (ADR-016).

Every add/change made through the console is written to the audit log with before/after values,
in the same transaction as the change. Deletion is disabled everywhere: records are
deactivated, revoked or corrected instead (spec 28.2). Versioned records get their version
bumped so API clients holding a stale copy receive 409 instead of overwriting console edits.
"""

from urllib.parse import urlencode

from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse

from apps.audit.services import model_changes, record_audit_event, snapshot
from common.pagination import CappedPaginator

from .site import can_use_console


def _audit_admin_change(request, obj, *, created: bool, before: dict | None = None, **extra):
    after = snapshot(obj)
    record_audit_event(
        action=f"admin.{obj._meta.model_name}.{'created' if created else 'updated'}",
        resource_type=obj._meta.model_name,
        resource_id=obj.pk,
        request=request,
        facility_id=getattr(obj, "facility_id", None)
        if obj._meta.model_name != "facility"
        else obj.pk,
        changes={"after": after} if created else model_changes(before or {}, after),
        metadata={"via": "admin-console", **extra},
    )


class _ConsolePermissions:
    def has_module_permission(self, request):
        return can_use_console(request.user)

    def has_view_permission(self, request, obj=None):
        return can_use_console(request.user)

    def has_add_permission(self, request, *args):
        return can_use_console(request.user)

    def has_change_permission(self, request, obj=None):
        return can_use_console(request.user)

    def has_delete_permission(self, request, obj=None):
        return False


class _OrganizationField:
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "organization":
            from apps.organizations.models import Organization
            from apps.organizations.selectors import get_deployment_organization

            organization = get_deployment_organization()
            kwargs["queryset"] = Organization.objects.filter(pk=organization.pk)
            kwargs["initial"] = organization.pk
            field = super().formfield_for_foreignkey(db_field, request, **kwargs)
            field.disabled = True  # always this deployment's organization
            return field
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class HimsModelAdmin(_OrganizationField, _ConsolePermissions, admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        for name in ("version", "created_at", "updated_at"):
            if any(f.name == name for f in self.model._meta.fields) and name not in readonly:
                readonly.append(name)
        return readonly

    def save_model(self, request, obj, form, change):
        before = snapshot(type(obj).objects.get(pk=obj.pk)) if change else None
        if change and hasattr(obj, "version"):
            obj.version += 1
        obj._hims_actor = request.user  # who, for records that keep their own history
        super().save_model(request, obj, form, change)
        _audit_admin_change(request, obj, created=not change, before=before)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        befores = {
            obj.pk: snapshot(type(obj).objects.get(pk=obj.pk))
            for obj in instances
            if obj.pk and not obj._state.adding
        }
        for obj in instances:
            if hasattr(obj, "organization_id") and not obj.organization_id:
                obj.organization_id = form.instance.organization_id
            created = obj._state.adding
            if not created and hasattr(obj, "version"):
                obj.version += 1  # API clients holding the old version now get 409
            obj._hims_actor = request.user
            obj.save()
            _audit_admin_change(request, obj, created=created, before=befores.get(obj.pk))
        formset.save_m2m()


class HimsInline(_OrganizationField, _ConsolePermissions, admin.TabularInline):
    extra = 0
    show_change_link = True


class HimsSettingsInline(HimsInline):
    """For pure settings rows (e.g. a department's weekly opening sessions) that may be removed.

    The only exception to "no deletion": these rows are configuration, not records of fact, and
    the parent admin must audit the before/after state in ``save_formset``.
    """

    def has_delete_permission(self, request, obj=None):
        return can_use_console(request.user)


class ConfirmIdentityAdminMixin:
    """Saving or running an action here needs a recent "confirm it's you" (HIMS-IAM-007; the
    same rule as the API). Looking does not. The person confirms and repeats what they did."""

    def _confirm_first(self, request):
        from apps.identity import confirmation

        if request.method != "POST" or confirmation.is_confirmed(request):
            return None
        messages.warning(request, "Nothing was changed yet. Confirm it's you, then do it again.")
        query = urlencode({"next": request.get_full_path()})
        return redirect(f"{reverse('admin:confirm_identity')}?{query}")

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        return self._confirm_first(request) or super().changeform_view(
            request, object_id, form_url, extra_context
        )

    def changelist_view(self, request, extra_context=None):
        return self._confirm_first(request) or super().changelist_view(request, extra_context)


class ReadOnlyModelAdmin(_ConsolePermissions, admin.ModelAdmin):
    """View-only registration for records the console must never edit."""

    def has_add_permission(self, request, *args):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class DepartmentListFilter(admin.RelatedFieldListFilter):
    """ "By department" with each department's facility loaded in the same query: a department's
    name shows its facility's code, which otherwise costs one query per department on every list
    page (found by HIMS-OPS-017)."""

    def field_choices(self, field, request, model_admin):
        ordering = self.field_admin_ordering(field, request, model_admin) or ("name",)
        departments = field.related_model._default_manager.select_related("facility")
        return [(department.pk, str(department)) for department in departments.order_by(*ordering)]


class LargeTableAdminMixin:
    """For the console's lists of the largest tables (audit log, messages, background events,
    sign-ins, issued numbers). Counting stops at 10,000 ("More than 10,000"), the second count of
    the whole table is skipped, and dates are filtered with Today / Past 7 days / This month
    instead of the date bar, whose year list reads the whole table. HIMS-OPS-017 measured the
    audit list at 1.9 s with 2 million events before this."""

    show_full_result_count = False
    paginator = CappedPaginator
