"""Doctor OPD schedules in the admin console (HIMS-OPD-001; ADR-016).

Sessions and exceptions are added through the same services as the app, so every rule applies
here too, and each change is in the audit log. Days and hours are never edited afterwards: end a
session and add a new one, or cancel an exception and record it again.
"""

from datetime import timedelta

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.forms.models import construct_instance

from apps.organizations.dates import hospital_today
from common.admin.options import DepartmentListFilter, HimsModelAdmin
from common.exceptions import DomainError

from . import services
from .models import DoctorSchedule, ScheduleException


def _saved_as(obj, saved) -> None:
    """The console shows the row the service saved (with the values it worked out)."""
    for field in saved._meta.concrete_fields:
        setattr(obj, field.attname, getattr(saved, field.attname))
    obj._state.adding = False


class DoctorScheduleForm(forms.ModelForm):
    class Meta:
        model = DoctorSchedule
        fields = (
            "staff",
            "department",
            "weekday",
            "start_time",
            "end_time",
            "slot_minutes",
            "extra_bookings_allowed",
            "valid_from",
            "valid_until",
            "note",
        )
        help_texts = {
            "staff": "A doctor posted in the department on the first day.",
            "valid_from": "The first day it may run (today or later).",
        }

    def _post_clean(self):
        # Only copy the values: services.schedule_problem (below) applies every rule, and the
        # database refuses overlaps. Django cannot pre-check this no-overlap rule from a form.
        self.instance = construct_instance(self, self.instance, self._meta.fields)

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        problem = services.schedule_problem(
            staff=data["staff"],
            department=data["department"],
            weekday=data["weekday"],
            start_time=data["start_time"],
            end_time=data["end_time"],
            slot_minutes=data["slot_minutes"],
            extra_bookings_allowed=data["extra_bookings_allowed"],
            valid_from=data["valid_from"],
            valid_until=data.get("valid_until"),
        )
        if problem:
            raise ValidationError(f"It cannot be added: {problem}.")
        return data


class SessionChangeForm(forms.ModelForm):
    class Meta:
        model = DoctorSchedule
        fields = ("slot_minutes", "extra_bookings_allowed", "note")

    def _post_clean(self):
        # services.change_session applies the rules (the times do not change here).
        self.instance = construct_instance(self, self.instance, self._meta.fields)


@admin.register(DoctorSchedule)
class DoctorScheduleAdmin(HimsModelAdmin):
    list_display = (
        "staff",
        "weekday",
        "start_time",
        "end_time",
        "department",
        "slot_minutes",
        "valid_from",
        "valid_until",
        "is_active",
    )
    # A department shows its facility's code: load both at once, not a query per row.
    list_select_related = ("staff", "department__facility")
    list_filter = ("weekday", "is_active", ("department", DepartmentListFilter))
    search_fields = ("staff__given_name", "staff__family_name", "staff__employee_number")
    autocomplete_fields = ("staff",)
    actions = ["end_today", "end_yesterday"]

    READ_ONLY = (
        "staff",
        "department",
        "weekday",
        "start_time",
        "end_time",
        "valid_from",
        "valid_until",
        "is_active",
        "created_by",
        "created_at",
        "ended_by",
        "ended_at",
        "end_reason",
        "version",
    )

    def get_form(self, request, obj=None, change=False, **kwargs):
        kwargs["form"] = DoctorScheduleForm if obj is None else SessionChangeForm
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return list(DoctorScheduleForm.Meta.fields)
        return [*self.READ_ONLY[:5], *SessionChangeForm.Meta.fields, *self.READ_ONLY[5:]]

    def get_readonly_fields(self, request, obj=None):
        return list(self.READ_ONLY) if obj is not None else []

    def save_model(self, request, obj, form, change):
        data = form.cleaned_data
        try:
            if change:
                services.change_session(
                    actor=request.user,
                    schedule_id=obj.pk,
                    version=DoctorSchedule.objects.get(pk=obj.pk).version,
                    request=request,
                    **{name: data[name] for name in SessionChangeForm.Meta.fields},
                )
                return
            created = services.add_sessions(
                actor=request.user,
                staff=data["staff"],
                department=data["department"],
                weekdays=[data["weekday"]],
                start_time=data["start_time"],
                end_time=data["end_time"],
                slot_minutes=data["slot_minutes"],
                extra_bookings_allowed=data["extra_bookings_allowed"],
                valid_from=data["valid_from"],
                valid_until=data.get("valid_until"),
                note=data.get("note", ""),
                request=request,
            )
        except DomainError as exc:
            raise ValidationError(str(exc.detail)) from exc
        _saved_as(obj, created[0])

    def _end(self, request, queryset, last_day, label):
        for schedule in queryset.select_related("department__facility"):
            try:
                services.end_session(
                    actor=request.user,
                    schedule_id=schedule.pk,
                    version=schedule.version,
                    last_day=last_day(schedule),
                    reason="Ended in the admin console",
                    request=request,
                )
                self.message_user(request, f"{schedule}: {label}.")
            except DomainError as exc:
                self.message_user(request, f"{schedule}: {exc.detail}", messages.ERROR)

    @admin.action(description="End selected sessions after today (today's still runs)")
    def end_today(self, request, queryset):
        self._end(request, queryset, lambda s: hospital_today(s.department.facility), "ends today")

    @admin.action(description="Stop selected sessions from today")
    def end_yesterday(self, request, queryset):
        self._end(
            request,
            queryset,
            lambda s: hospital_today(s.department.facility) - timedelta(days=1),
            "stopped from today",
        )


class ScheduleExceptionForm(forms.ModelForm):
    class Meta:
        model = ScheduleException
        fields = (
            "kind",
            "staff",
            "facility",
            "department",
            "start_date",
            "end_date",
            "start_time",
            "end_time",
            "slot_minutes",
            "extra_bookings_allowed",
            "reason",
        )
        help_texts = {
            "staff": "The doctor (doctor away, extra session). Empty for a holiday.",
            "department": "Doctor away or extra session: required. Holiday: empty = the whole "
            "facility.",
            "end_date": "Empty = one day.",
            "start_time": "Empty = the whole day (an extra session needs its hours).",
            "slot_minutes": "Extra session only (default 10).",
            "extra_bookings_allowed": "Extra session only (default 0).",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["end_date"].required = False

    def _post_clean(self):
        self.instance = construct_instance(self, self.instance, self._meta.fields)

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        item = services.new_exception(**self.service_values(data))
        problem = services.exception_problem(item)
        if problem:
            raise ValidationError(f"It cannot be recorded: {problem}.")
        return data

    @staticmethod
    def service_values(data) -> dict:
        return {name: data.get(name) for name in ScheduleExceptionForm.Meta.fields} | {
            "reason": data.get("reason") or ""
        }


@admin.register(ScheduleException)
class ScheduleExceptionAdmin(HimsModelAdmin):
    list_display = (
        "kind",
        "staff",
        "facility",
        "department",
        "start_date",
        "end_date",
        "start_time",
        "end_time",
        "status",
    )
    list_select_related = ("staff", "facility", "department__facility")
    list_filter = ("kind", "status", "facility", ("department", DepartmentListFilter))
    search_fields = ("staff__given_name", "staff__family_name", "reason")
    date_hierarchy = "start_date"
    autocomplete_fields = ("staff",)
    actions = ["cancel_selected"]

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            kwargs["form"] = ScheduleExceptionForm
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return list(ScheduleExceptionForm.Meta.fields)
        return [
            *ScheduleExceptionForm.Meta.fields,
            "status",
            "created_by",
            "created_at",
            "cancelled_by",
            "cancelled_at",
            "cancel_reason",
            "version",
        ]

    def get_readonly_fields(self, request, obj=None):
        return self.get_fields(request, obj) if obj is not None else []

    def save_model(self, request, obj, form, change):
        if change:
            return  # cancel with the action and record again instead of editing
        try:
            item, _ = services.add_exception(
                actor=request.user,
                request=request,
                **ScheduleExceptionForm.service_values(form.cleaned_data),
            )
        except DomainError as exc:
            raise ValidationError(str(exc.detail)) from exc
        _saved_as(obj, item)

    @admin.action(description="Cancel selected exceptions")
    def cancel_selected(self, request, queryset):
        for item in queryset:
            try:
                services.cancel_exception(
                    actor=request.user,
                    exception_id=item.pk,
                    version=item.version,
                    reason="Cancelled in the admin console",
                    request=request,
                )
                self.message_user(request, f"{item}: cancelled.")
            except DomainError as exc:
                self.message_user(request, f"{item}: {exc.detail}", messages.ERROR)
