"""Rotas, on-call and leave in the admin console (HIMS-STAFF-012; ADR-016).

Shifts and leave are added through the same services as the app, so every rule applies here
too. They are never edited afterwards: cancel and plan again, or decide with the actions.
"""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.forms.models import construct_instance

from common.admin.options import HimsModelAdmin
from common.exceptions import DomainError

from . import services
from .models import LeaveRequest, Shift, ShiftType


@admin.register(ShiftType)
class ShiftTypeAdmin(HimsModelAdmin):
    """Codes never change once created; times apply to shifts planned afterwards."""

    list_display = ("name", "kind", "start_time", "end_time", "is_custom", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("code", "name")

    def get_readonly_fields(self, request, obj=None):
        readonly = [*super().get_readonly_fields(request, obj), "is_custom"]
        if obj is not None:
            readonly.append("code")
        return readonly

    def save_model(self, request, obj, form, change):
        if not change:
            obj.is_custom = True
        super().save_model(request, obj, form, change)


class ShiftForm(forms.ModelForm):
    class Meta:
        model = Shift
        fields = ("staff", "department", "shift_type", "on_date", "note")
        help_texts = {"on_date": "The day the shift starts, at the department's facility."}

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        problem, _, _ = services.shift_problem(
            staff=data["staff"],
            department=data["department"],
            shift_type=data["shift_type"],
            on_date=data["on_date"],
        )
        if problem:
            raise ValidationError(f"It cannot be planned: {problem}.")
        return data


@admin.register(Shift)
class ShiftAdmin(HimsModelAdmin):
    list_display = ("staff", "shift_type", "on_date", "department", "status", "starts_at")
    list_filter = ("status", "shift_type", "department")
    search_fields = ("staff__given_name", "staff__family_name", "staff__employee_number")
    date_hierarchy = "on_date"
    autocomplete_fields = ("staff",)
    actions = ["cancel_selected"]

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            kwargs["form"] = ShiftForm
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return list(ShiftForm.Meta.fields)
        return [
            "staff",
            "department",
            "shift_type",
            "on_date",
            "starts_at",
            "ends_at",
            "note",
            "status",
            "created_by",
            "created_at",
            "cancelled_at",
            "cancelled_by",
            "cancel_reason",
            "version",
        ]

    def get_readonly_fields(self, request, obj=None):
        return self.get_fields(request, obj) if obj is not None else []

    def save_model(self, request, obj, form, change):
        if change:
            return  # cancel with the action and plan again instead of editing
        data = form.cleaned_data
        created, skipped = services.add_shifts(
            actor=request.user,
            staff=data["staff"],
            department=data["department"],
            shift_type=data["shift_type"],
            from_date=data["on_date"],
            to_date=data["on_date"],
            note=data.get("note", ""),
            request=request,
        )
        if not created:
            raise ValidationError(skipped[0]["reason"])
        obj.pk = created[0].pk
        obj._state.adding = False

    @admin.action(description="Cancel selected shifts")
    def cancel_selected(self, request, queryset):
        for shift in queryset:
            try:
                services.cancel_shift(
                    actor=request.user,
                    shift_id=shift.pk,
                    version=shift.version,
                    reason="Cancelled in the admin console",
                    request=request,
                )
                self.message_user(request, f"{shift}: cancelled.")
            except DomainError as exc:
                self.message_user(request, f"{shift}: {exc.detail}", messages.ERROR)


class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ("staff", "department", "leave_type", "start_date", "end_date", "reason")
        help_texts = {"reason": "Optional. No medical details: the kind of leave is enough."}

    def _post_clean(self):
        # Only copy the values: services.check_leave (below) applies every rule, and the
        # database refuses overlaps. Django cannot pre-check this no-overlap rule from a form.
        self.instance = construct_instance(self, self.instance, self._meta.fields)

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        try:
            services.check_leave(
                staff=data["staff"],
                department=data["department"],
                start_date=data["start_date"],
                end_date=data["end_date"],
            )
        except DomainError as exc:
            raise ValidationError(str(exc.detail)) from exc
        return data


@admin.register(LeaveRequest)
class LeaveRequestAdmin(HimsModelAdmin):
    """Leave recorded here still needs a decision by someone other than the person."""

    list_display = ("staff", "leave_type", "start_date", "end_date", "status", "department")
    list_filter = ("status", "leave_type", "department")
    search_fields = ("staff__given_name", "staff__family_name", "staff__employee_number")
    date_hierarchy = "start_date"
    autocomplete_fields = ("staff",)
    actions = [
        "approve_selected",
        "approve_cancelling_shifts",
        "reject_selected",
        "cancel_selected",
    ]

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            kwargs["form"] = LeaveRequestForm
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return list(LeaveRequestForm.Meta.fields)
        return [
            "staff",
            "department",
            "leave_type",
            "start_date",
            "end_date",
            "reason",
            "status",
            "requested_by",
            "created_at",
            "decided_by",
            "decided_at",
            "decision_note",
            "cancelled_by",
            "cancelled_at",
            "cancel_reason",
            "version",
        ]

    def get_readonly_fields(self, request, obj=None):
        return self.get_fields(request, obj) if obj is not None else []

    def save_model(self, request, obj, form, change):
        if change:
            return  # decide with the actions
        data = form.cleaned_data
        try:
            leave = services.request_leave(
                actor=request.user,
                staff=data["staff"],
                department=data["department"],
                leave_type=data["leave_type"],
                start_date=data["start_date"],
                end_date=data["end_date"],
                reason=data.get("reason", ""),
                request=request,
            )
        except DomainError as exc:
            raise ValidationError(str(exc.detail)) from exc
        obj.pk = leave.pk
        obj._state.adding = False

    def _each(self, request, queryset, call, done: str):
        for leave in queryset:
            try:
                call(leave)
                self.message_user(request, f"{leave}: {done}.")
            except DomainError as exc:
                self.message_user(request, f"{leave}: {exc.detail}", messages.ERROR)

    @admin.action(description="Approve selected leave")
    def approve_selected(self, request, queryset):
        self._each(
            request,
            queryset,
            lambda leave: services.approve_leave(
                actor=request.user, leave_id=leave.pk, version=leave.version, request=request
            ),
            "approved",
        )

    @admin.action(description="Approve selected leave and cancel their shifts on those days")
    def approve_cancelling_shifts(self, request, queryset):
        self._each(
            request,
            queryset,
            lambda leave: services.approve_leave(
                actor=request.user,
                leave_id=leave.pk,
                version=leave.version,
                cancel_shifts=True,
                request=request,
            ),
            "approved, shifts cancelled",
        )

    @admin.action(description="Refuse selected leave")
    def reject_selected(self, request, queryset):
        self._each(
            request,
            queryset,
            lambda leave: services.reject_leave(
                actor=request.user,
                leave_id=leave.pk,
                version=leave.version,
                note="Refused in the admin console",
                request=request,
            ),
            "refused",
        )

    @admin.action(description="Cancel selected leave")
    def cancel_selected(self, request, queryset):
        self._each(
            request,
            queryset,
            lambda leave: services.cancel_leave(
                actor=request.user,
                leave_id=leave.pk,
                version=leave.version,
                reason="Cancelled in the admin console",
                as_approver=True,
                request=request,
            ),
            "cancelled",
        )
