"""Base ModelAdmin classes for the HIMS console (ADR-016).

Every add/change made through the console is written to the audit log with before/after values,
in the same transaction as the change. Deletion is disabled everywhere: records are
deactivated, revoked or corrected instead (spec 28.2). Versioned records get their version
bumped so API clients holding a stale copy receive 409 instead of overwriting console edits.
"""

from django.contrib import admin

from apps.audit.services import model_changes, record_audit_event, snapshot

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
            obj.save()
            _audit_admin_change(request, obj, created=created, before=befores.get(obj.pk))
        formset.save_m2m()


class HimsInline(_OrganizationField, _ConsolePermissions, admin.TabularInline):
    extra = 0
    show_change_link = True


class ReadOnlyModelAdmin(_ConsolePermissions, admin.ModelAdmin):
    """View-only registration for records the console must never edit."""

    def has_add_permission(self, request, *args):
        return False

    def has_change_permission(self, request, obj=None):
        return False
