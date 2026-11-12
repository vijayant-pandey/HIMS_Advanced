"""Rotas, on-call and leave in the admin console (HIMS-STAFF-012; ADR-016).

Shifts and leave are added through the same services as the app, so every rule applies here
too. They are never edited afterwards: cancel and plan again, or decide with the actions.
"""

from datetime import timedelta

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.forms.models import construct_instance
from django.template.response import TemplateResponse
from django.urls import path

from apps.facilities.models import Department
from apps.organizations.dates import hospital_today
from common.admin.options import DepartmentListFilter, HimsModelAdmin, ReadOnlyModelAdmin
from common.exceptions import DomainError

from . import balances, services, staffing
from .models import (
    LeaveBalanceAdjustment,
    LeaveEntitlement,
    LeaveRequest,
    Shift,
    ShiftType,
    StaffingGapAlert,
    StaffingRequirement,
)

GAP_PAGE_DAYS = 14


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
    # A department shows its facility's code: load both at once, not a query per row (HIMS-OPS-017).
    list_select_related = ("staff", "shift_type", "department__facility")
    list_filter = ("status", "shift_type", ("department", DepartmentListFilter))
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

    # "Copy a week", as on the Rota page (same service and rules; gap found 2026-11-12).
    def get_urls(self):
        return [
            path(
                "copy-week/",
                self.admin_site.admin_view(self.copy_week_view),
                name="rosters_shift_copy_week",
            ),
            *super().get_urls(),
        ]

    def copy_week_view(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        form = CopyWeekForm(request.POST or None)
        result = None
        if request.method == "POST" and form.is_valid():
            data = form.cleaned_data
            try:
                created, skipped = services.copy_week(
                    actor=request.user,
                    department=data["department"],
                    from_start=data["from_start"],
                    to_start=data["to_start"],
                    request=request,
                )
                result = {"created": len(created), "skipped": skipped}
            except DomainError as exc:
                form.add_error(None, str(exc.detail))
        context = {
            **self.admin_site.each_context(request),
            "title": "Copy a week of shifts",
            "form": form,
            "result": result,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/rosters/shift/copy_week.html", context)


class CopyWeekForm(forms.Form):
    department = forms.ModelChoiceField(
        queryset=Department.objects.filter(status=Department.Status.ACTIVE)
        .select_related("facility")
        .order_by("facility__name", "name")
    )
    from_start = forms.DateField(help_text="First day of the week to copy.")
    to_start = forms.DateField(help_text="Same weekday, one or more weeks later.")


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
    # A department shows its facility's code: load both at once, not a query per row (HIMS-OPS-017).
    list_select_related = ("staff", "department__facility")
    list_filter = ("status", "leave_type", ("department", DepartmentListFilter))
    search_fields = ("staff__given_name", "staff__family_name", "staff__employee_number")
    date_hierarchy = "start_date"
    autocomplete_fields = ("staff",)
    actions = [
        "approve_selected",
        "approve_cancelling_shifts",
        "approve_over_balance",
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

    @admin.action(description="Approve selected leave even if it goes over the balance")
    def approve_over_balance(self, request, queryset):
        self._each(
            request,
            queryset,
            lambda leave: services.approve_leave(
                actor=request.user,
                leave_id=leave.pk,
                version=leave.version,
                note="Approved over the balance in the admin console",
                allow_over_balance=True,
                request=request,
            ),
            "approved",
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


@admin.register(StaffingRequirement)
class StaffingRequirementAdmin(HimsModelAdmin):
    """The hospital's minimum people per shift (HIMS-STAFF-015). A gap warns; it never blocks."""

    change_list_template = "admin/rosters/staffingrequirement/change_list.html"
    list_display = ("department", "shift_type", "staff_type", "applies_on", "minimum", "is_active")
    # A department shows its facility's code: load both at once, not a query per row (HIMS-OPS-017).
    list_select_related = ("department__facility", "shift_type")
    list_filter = ("is_active", ("department", DepartmentListFilter), "shift_type")
    fields = (
        "department",
        "shift_type",
        "staff_type",
        "applies_on",
        "minimum",
        "is_active",
        "version",
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        return (
            [*readonly, "department", "shift_type", "staff_type", "applies_on"] if obj else readonly
        )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.organization_id = obj.department.organization_id
            obj.facility_id = obj.department.facility_id
        super().save_model(request, obj, form, change)

    def get_urls(self):
        return [
            path(
                "gaps/",
                self.admin_site.admin_view(self.gaps_view),
                name="rosters_staffingrequirement_gaps",
            ),
            *super().get_urls(),
        ]

    def gaps_view(self, request):
        """Every shift below the minimum in the next two weeks, department by department."""
        departments = Department.objects.filter(
            pk__in=StaffingRequirement.objects.filter(is_active=True).values("department_id")
        ).select_related("facility")
        rows = []
        for department in departments.order_by("name"):
            first = hospital_today(department.facility)
            last = first + timedelta(days=GAP_PAGE_DAYS - 1)
            rows += [
                {"department": department.name, **gap}
                for gap in staffing.gaps(department, first, last)
            ]
        context = {
            **self.admin_site.each_context(request),
            "title": "Staffing gaps in the next two weeks",
            "rows": rows,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/rosters/staffingrequirement/gaps.html", context)


@admin.register(StaffingGapAlert)
class StaffingGapAlertAdmin(ReadOnlyModelAdmin):
    """Gaps already emailed to planners, so each is told once."""

    list_display = ("on_date", "department", "shift_type", "staff_type", "sent_at")
    # A department shows its facility's code: load both at once, not a query per row (HIMS-OPS-017).
    list_select_related = ("department__facility", "shift_type")
    list_filter = (("department", DepartmentListFilter), "shift_type")
    date_hierarchy = "on_date"


class LeaveEntitlementForm(forms.ModelForm):
    class Meta:
        model = LeaveEntitlement
        fields = (
            "leave_type",
            "from_year",
            "days",
            "max_carry_over",
            "prorate_on_joining",
            "tracked",
        )

    def clean_from_year(self):
        year = self.cleaned_data["from_year"]
        if self.instance._state.adding and year < balances.current_year():
            raise ValidationError(
                "An entitlement starts this leave year or later. For balances brought from "
                "before, add a leave balance adjustment."
            )
        return year


@admin.register(LeaveEntitlement)
class LeaveEntitlementAdmin(HimsModelAdmin):
    """Same rule as the app: rows started in an earlier year stay as they are, so past balances
    do not change. Add a new one from this year instead."""

    form = LeaveEntitlementForm
    list_display = ("leave_type", "from_year", "days", "max_carry_over", "tracked", "updated_by")
    list_filter = ("leave_type", "tracked")

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        return [*readonly, "leave_type", "from_year"] if obj else readonly

    def has_change_permission(self, request, obj=None):
        allowed = super().has_change_permission(request, obj)
        return allowed and (obj is None or obj.from_year >= balances.current_year())

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


class LeaveAdjustmentForm(forms.ModelForm):
    actor = None  # set by the admin for this request

    class Meta:
        model = LeaveBalanceAdjustment
        fields = ("staff", "leave_type", "leave_year", "days", "reason")

    def _post_clean(self):
        # Only copy the values: balances.check_adjustment (below) applies every rule.
        self.instance = construct_instance(self, self.instance, self._meta.fields)

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        try:
            balances.check_adjustment(
                actor=self.actor,
                staff=data["staff"],
                leave_type=data["leave_type"],
                leave_year=data["leave_year"],
                days=data["days"],
                reason=data["reason"],
            )
        except DomainError as exc:
            raise ValidationError(str(exc.detail)) from exc
        return data


@admin.register(LeaveBalanceAdjustment)
class LeaveBalanceAdjustmentAdmin(HimsModelAdmin):
    """Add one through the same rules as the app. They cannot be changed: a wrong one is corrected
    by another."""

    form = LeaveAdjustmentForm
    list_display = ("created_at", "staff", "leave_type", "leave_year", "days", "created_by")
    list_filter = ("leave_type", "leave_year")
    search_fields = ("staff__given_name", "staff__family_name", "staff__employee_number")
    autocomplete_fields = ("staff",)

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change=change, **kwargs)
        form.actor = request.user
        return form

    def has_change_permission(self, request, obj=None):
        return obj is None and super().has_change_permission(request, obj)

    def get_fields(self, request, obj=None):
        fields = list(LeaveAdjustmentForm.Meta.fields)
        return [*fields, "created_by", "created_at"] if obj is not None else fields

    def get_readonly_fields(self, request, obj=None):
        return self.get_fields(request, obj) if obj is not None else []

    def save_model(self, request, obj, form, change):
        data = form.cleaned_data
        try:
            row = balances.adjust_balance(
                actor=request.user,
                staff=data["staff"],
                leave_type=data["leave_type"],
                leave_year=data["leave_year"],
                days=data["days"],
                reason=data["reason"],
                request=request,
            )
        except DomainError as exc:
            raise ValidationError(str(exc.detail)) from exc
        obj.pk = row.pk
        obj._state.adding = False
