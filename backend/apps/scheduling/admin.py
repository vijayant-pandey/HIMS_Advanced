"""Doctor OPD schedules, appointments and the OPD queue in the admin console (HIMS-OPD-001,
HIMS-OPD-002, HIMS-OPD-003; ADR-016).

Sessions, exceptions and appointments go through the same services as the app, so every rule
applies here too, and each change is in the audit log. Days and hours are never edited
afterwards: end a session and add a new one, or cancel an exception and record it again. An
appointment is booked, moved (its own page) or cancelled (actions), never edited. On the day,
patients are checked in, marked seen, left or did not come (actions); the **OPD queue** page calls
the next patient and checks in walk-ins.
"""

from datetime import datetime, timedelta

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import F, Value
from django.forms.models import construct_instance
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse

from apps.facilities.models import Department
from apps.organizations.dates import hospital_timezone, hospital_today
from apps.patients import restricted
from apps.patients.models import Patient
from apps.staff.models import StaffMember
from common.admin.options import DepartmentListFilter, HimsModelAdmin, LargeTableAdminMixin
from common.exceptions import DomainError

from . import booking, opd_queue, selectors, services
from .models import Appointment, DoctorSchedule, ScheduleException


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


# --- Appointments (HIMS-OPD-002) ---------------------------------------------------------------


def _starts_at(department, day, clock) -> datetime:
    """A day and a time on the department's facility clock, as an instant."""
    return datetime.combine(day, clock, tzinfo=hospital_timezone(department.facility))


def _doctors():
    return StaffMember.objects.filter(
        staff_type__in=services.OPD_STAFF_TYPES,
        employment_status=StaffMember.EmploymentStatus.ACTIVE,
    ).order_by("family_name", "given_name")


def _departments():
    return (
        Department.objects.filter(status=Department.Status.ACTIVE)
        .select_related("facility")
        .order_by("facility__name", "name")
    )


class AppointmentForm(forms.ModelForm):
    day = forms.DateField(help_text="The appointment day.")
    time = forms.TimeField(
        help_text="A free slot's start on the facility's clock, e.g. 09:10 (see the Appointments "
        "page in the app for the free slots)."
    )

    class Meta:
        model = Appointment
        fields = ("patient", "staff", "department", "kind", "source", "reason", "is_extra")
        labels = {"staff": "Doctor", "is_extra": "Over the slots (extra booking)"}
        help_texts = {
            "reason": "Short; no detailed history.",
            "is_extra": "Only into a booked slot, when the session allows extra bookings.",
        }

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request

    def _post_clean(self):
        # Only copy the values: booking.check_booking (below) applies every rule, and the
        # database refuses double bookings. Django cannot pre-check that rule from a form.
        self.instance = construct_instance(self, self.instance, self._meta.fields)

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        if self.request is not None:
            try:
                restricted.opening(self.request.user, data["patient"])
            except DomainError as exc:
                raise ValidationError(str(exc.detail)) from exc
        check = booking.check_booking(
            patient=data["patient"],
            staff=data["staff"],
            department=data["department"],
            starts_at=_starts_at(data["department"], data["day"], data["time"]),
            extra=data["is_extra"],
        )
        if check.problem:
            raise ValidationError(f"It cannot be booked: {check.problem}")
        return data


class MoveForm(forms.Form):
    day = forms.DateField()
    time = forms.TimeField(help_text="A free slot's start on the facility's clock.")
    staff = forms.ModelChoiceField(
        queryset=StaffMember.objects.none(),
        required=False,
        label="Doctor",
        help_text="Empty = the same doctor.",
    )
    extra = forms.BooleanField(required=False, label="Over the slots (extra booking)")
    note = forms.CharField(max_length=255, required=False, help_text="Optional. Why it moves.")

    def __init__(self, *args, appointment, **kwargs):
        super().__init__(*args, **kwargs)
        self.appointment = appointment
        self.fields["staff"].queryset = _doctors()

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        old = self.appointment
        staff = data.get("staff") or old.staff
        starts_at = _starts_at(old.department, data["day"], data["time"])
        if staff.pk == old.staff_id and starts_at == old.starts_at:
            raise ValidationError("That is the time it already has.")
        check = booking.check_booking(
            patient=old.patient,
            staff=staff,
            department=old.department,
            starts_at=starts_at,
            extra=data["extra"],
            moving=old,
        )
        if check.problem:
            raise ValidationError(f"It cannot be moved there: {check.problem}")
        data["starts_at"] = starts_at
        return data


class ToMoveForm(forms.Form):
    """Choose a department (the Appointments to move and the OPD queue pages)."""

    department = forms.ModelChoiceField(queryset=Department.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = _departments()


class WalkInForm(forms.Form):
    """A walk-in on the console's OPD queue page (HIMS-OPD-003)."""

    mrn = forms.CharField(label="Patient's MRN", max_length=40, help_text="The exact MRN.")
    staff = forms.ModelChoiceField(queryset=StaffMember.objects.none(), label="Doctor")
    kind = forms.ChoiceField(choices=Appointment.Kind.choices, label="Visit")
    reason = forms.CharField(
        max_length=200, required=False, help_text="Optional. Short; no detailed history."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["staff"].queryset = _doctors()

    def clean_mrn(self):
        patient = Patient.objects.filter(mrn=self.cleaned_data["mrn"].strip()).first()
        if patient is None:
            raise ValidationError("No patient has this MRN.")
        return patient


@admin.register(Appointment)
class AppointmentAdmin(LargeTableAdminMixin, HimsModelAdmin):
    """Appointments: a large table, so counts stop at 10,000 and dates use quick filters."""

    list_display = (
        "local_date",
        "time",
        "token_number",
        "patient_shown",
        "staff",
        "department",
        "status",
        "kind",
        "source",
        "is_extra",
    )
    list_select_related = ("patient", "staff", "department__facility", "facility")
    list_filter = (
        "status",
        "kind",
        "source",
        "facility",
        ("department", DepartmentListFilter),
        ("starts_at", admin.DateFieldListFilter),
    )
    search_fields = ("=patient__mrn",)
    search_help_text = "The patient's exact MRN."
    ordering = ("-starts_at",)  # appointment_start_idx
    autocomplete_fields = ("patient", "staff")
    actions = [
        "cancel_patient_request",
        "cancel_hospital",
        "cancel_doctor_unavailable",
        "check_in",
        "mark_seen",
        "left_unseen",
        "mark_no_show",
        "undo_no_show",
    ]
    change_form_template = "admin/scheduling/appointment/change_form.html"
    change_list_template = "admin/scheduling/appointment/change_list.html"

    READ_ONLY = (
        "patient_shown",
        "staff",
        "department",
        "facility",
        "starts_at",
        "ends_at",
        "local_date",
        "kind",
        "source",
        "status",
        "reason_shown",
        "is_extra",
        "schedule",
        "extra_session",
        "rescheduled_from",
        "moved_to",
        "booked_by",
        "created_at",
        "cancel_reason",
        "cancel_note",
        "cancelled_by",
        "cancelled_at",
        "token_number",
        "checked_in_at",
        "checked_in_by",
        "called_at",
        "seen_at",
        "version",
    )

    def get_queryset(self, request):
        """Each row says whether its patient's name is hidden from this person (a restricted
        record, HIMS-PAT-006), worked out per request."""
        rows = super().get_queryset(request)
        if restricted.may_see_restricted(request.user):
            return rows.annotate(hide_patient=Value(False))
        return rows.annotate(hide_patient=F("patient__is_restricted"))

    @staticmethod
    def _hidden(obj) -> bool:
        return getattr(obj, "hide_patient", obj.patient.is_restricted)

    @admin.display(description="Patient", ordering="patient__mrn")
    def patient_shown(self, obj):
        if self._hidden(obj):
            return f"{obj.patient.mrn} (restricted record)"
        return str(obj.patient)

    @admin.display(description="Reason")
    def reason_shown(self, obj):
        return "" if self._hidden(obj) else obj.reason

    @admin.display(description="Time")
    def time(self, obj):
        return f"{obj.starts_at.astimezone(hospital_timezone(obj.facility)):%H:%M}"

    @admin.display(description="Moved to")
    def moved_to(self, obj):
        moved = Appointment.objects.filter(rescheduled_from=obj).first()
        return str(moved.local_date) + f" {self.time(moved)}" if moved else "-"

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            kwargs["form"] = AppointmentForm
            form = super().get_form(request, obj, change=change, **kwargs)

            class WithRequest(form):
                def __init__(self, *args, **kw):
                    super().__init__(*args, request=request, **kw)

            return WithRequest
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return [
                *AppointmentForm.Meta.fields[:3],
                "day",
                "time",
                *AppointmentForm.Meta.fields[3:],
            ]
        return list(self.READ_ONLY)

    def get_readonly_fields(self, request, obj=None):
        return list(self.READ_ONLY) if obj is not None else []

    def save_model(self, request, obj, form, change):
        if change:
            return  # moved on its own page or cancelled with an action, never edited
        data = form.cleaned_data
        try:
            created = booking.book(
                actor=request.user,
                patient=data["patient"],
                staff=data["staff"],
                department=data["department"],
                starts_at=_starts_at(data["department"], data["day"], data["time"]),
                kind=data["kind"],
                source=data["source"],
                reason=data.get("reason") or "",
                extra=data["is_extra"],
                request=request,
            )
        except DomainError as exc:
            raise ValidationError(str(exc.detail)) from exc
        _saved_as(obj, created)

    def get_urls(self):
        return [
            path(
                "<uuid:object_id>/move/",
                self.admin_site.admin_view(self.move_view),
                name="scheduling_appointment_move",
            ),
            path(
                "to-move/",
                self.admin_site.admin_view(self.to_move_view),
                name="scheduling_appointment_to_move",
            ),
            path(
                "queue/",
                self.admin_site.admin_view(self.queue_view),
                name="scheduling_appointment_queue",
            ),
            *super().get_urls(),
        ]

    def move_view(self, request, object_id):
        """Move a booked appointment to another slot, as on the Appointments page."""
        appointment = get_object_or_404(
            self.get_queryset(request).select_related("patient", "staff", "department__facility"),
            pk=object_id,
        )
        if not self.has_change_permission(request, appointment):
            raise PermissionDenied
        try:
            restricted.opening(request.user, appointment.patient)
        except DomainError as exc:
            raise PermissionDenied(str(exc.detail)) from exc
        form = MoveForm(request.POST or None, appointment=appointment)
        if appointment.status != Appointment.Status.BOOKED:
            form = None
        elif request.method == "POST" and form.is_valid():
            data = form.cleaned_data
            try:
                new = booking.reschedule(
                    actor=request.user,
                    appointment_id=appointment.pk,
                    version=appointment.version,
                    starts_at=data["starts_at"],
                    staff=data.get("staff"),
                    extra=data["extra"],
                    note=data.get("note") or "",
                    request=request,
                )
            except DomainError as exc:
                form.add_error(None, str(exc.detail))
            else:
                self.message_user(request, f"Moved to {new.local_date:%d %b %Y} {self.time(new)}.")
                return HttpResponseRedirect(
                    reverse("admin:scheduling_appointment_change", args=[new.pk])
                )
        context = {
            **self.admin_site.each_context(request),
            "title": "Move an appointment",
            "appointment": appointment,
            "patient": self.patient_shown(appointment),
            "when": f"{appointment.local_date:%d %b %Y} {self.time(appointment)}",
            "form": form,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/scheduling/appointment/move.html", context)

    def to_move_view(self, request):
        """Booked patients whose doctor is now away or whose session is off, as on the
        Appointments page's "To move" list."""
        form = ToMoveForm(request.GET or None)
        rows = None
        if form.is_valid():
            rows = selectors.to_rebook(form.cleaned_data["department"], details=True)
            if not restricted.may_see_restricted(request.user):
                for row in rows:
                    row["appointment"].hide_patient = row["appointment"].patient.is_restricted
        context = {
            **self.admin_site.each_context(request),
            "title": "Appointments to move",
            "form": form,
            "rows": [
                {
                    "appointment": row["appointment"],
                    "patient": self.patient_shown(row["appointment"]),
                    "time": self.time(row["appointment"]),
                    "why": row["why"],
                }
                for row in rows or []
            ],
            "shown": rows is not None,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/scheduling/appointment/to_move.html", context)

    def _cancel(self, request, queryset, reason):
        for appointment in queryset.select_related("patient", "department__facility"):
            try:
                restricted.opening(request.user, appointment.patient)
                booking.cancel(
                    actor=request.user,
                    appointment_id=appointment.pk,
                    version=appointment.version,
                    reason=reason,
                    note="Cancelled in the admin console",
                    request=request,
                )
                self.message_user(request, f"{appointment.patient.mrn}: cancelled.")
            except DomainError as exc:
                self.message_user(
                    request, f"{appointment.patient.mrn}: {exc.detail}", messages.ERROR
                )

    @admin.action(description="Cancel selected: the patient asked")
    def cancel_patient_request(self, request, queryset):
        self._cancel(request, queryset, Appointment.CancelReason.PATIENT_REQUEST)

    @admin.action(description="Cancel selected: the hospital cancelled")
    def cancel_hospital(self, request, queryset):
        self._cancel(request, queryset, Appointment.CancelReason.HOSPITAL)

    @admin.action(description="Cancel selected: the doctor is not available")
    def cancel_doctor_unavailable(self, request, queryset):
        self._cancel(request, queryset, Appointment.CancelReason.DOCTOR_UNAVAILABLE)

    # --- The OPD queue (HIMS-OPD-003) -------------------------------------------------------

    def _step(self, request, queryset, service, done: str, *, opening=False):
        for appointment in queryset.select_related("patient"):
            try:
                if opening:
                    restricted.opening(request.user, appointment.patient)
                service(
                    actor=request.user,
                    appointment_id=appointment.pk,
                    version=appointment.version,
                    request=request,
                )
                self.message_user(request, f"{appointment.patient.mrn}: {done}.")
            except DomainError as exc:
                self.message_user(
                    request, f"{appointment.patient.mrn}: {exc.detail}", messages.ERROR
                )

    @admin.action(description="Check in selected (today: each gets the doctor's next token)")
    def check_in(self, request, queryset):
        self._step(request, queryset, opd_queue.check_in, "checked in", opening=True)

    @admin.action(description="Mark selected: seen by the doctor")
    def mark_seen(self, request, queryset):
        self._step(request, queryset, opd_queue.mark_seen, "seen")

    @admin.action(description="Mark selected: left before being seen")
    def left_unseen(self, request, queryset):
        self._step(request, queryset, opd_queue.left_unseen, "left before being seen")

    @admin.action(description="Mark selected: the patient did not come")
    def mark_no_show(self, request, queryset):
        self._step(request, queryset, opd_queue.mark_no_show, "marked as not come")

    @admin.action(description="Undo did not come (the same day, before the session ends)")
    def undo_no_show(self, request, queryset):
        self._step(request, queryset, opd_queue.undo_no_show, "booked again")

    def _queue_post(self, request, department):
        """Call next (one doctor) or a walk-in; returns the walk-in form (with its errors)."""
        walk_in = WalkInForm(request.POST if "walk_in" in request.POST else None)
        try:
            if "call_next" in request.POST:
                staff = get_object_or_404(_doctors(), pk=request.POST["call_next"])
                result = opd_queue.call_next(
                    actor=request.user, staff=staff, department=department, request=request
                )
                called = result["called"]
                self.message_user(
                    request,
                    f"Token {called.token_number} called in to {staff}."
                    if called
                    else f"{staff}: the patient with the doctor is seen; nobody is waiting.",
                )
            elif walk_in.is_valid():
                data = walk_in.cleaned_data
                restricted.opening(request.user, data["mrn"])
                created = opd_queue.walk_in(
                    actor=request.user,
                    patient=data["mrn"],
                    staff=data["staff"],
                    department=department,
                    kind=data["kind"],
                    reason=data.get("reason") or "",
                    request=request,
                )
                self.message_user(
                    request, f"{data['mrn'].mrn}: checked in, token {created.token_number}."
                )
                walk_in = WalkInForm()
        except DomainError as exc:
            self.message_user(request, str(exc.detail), messages.ERROR)
        return walk_in

    def queue_view(self, request):
        """Today's OPD queue in one department, as on the OPD queue page: call the next patient
        for a doctor, check in a walk-in. Check-in and the rest are actions on the list."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        form = ToMoveForm(request.GET or None)
        walk_in = WalkInForm()
        data = None
        if form.is_valid():
            department = form.cleaned_data["department"]
            if request.method == "POST":
                if not self.has_change_permission(request):
                    raise PermissionDenied
                walk_in = self._queue_post(request, department)
            data = selectors.queue_day(
                department, hospital_today(department.facility), details=True
            )
            if not restricted.may_see_restricted(request.user):
                for appointment in data["appointments"]:
                    appointment.hide_patient = appointment.patient.is_restricted
        doctors = []
        for doctor in (data or {}).get("doctors", []):
            mine = [a for a in data["appointments"] if a.staff_id == doctor["staff_id"]]
            doctors.append(
                {
                    "staff_id": doctor["staff_id"],
                    "name": doctor["name"],
                    "hours": ", ".join(s["hours"] for s in doctor["sessions"]) or "No session",
                    "rows": [
                        {
                            "appointment": a,
                            "patient": self.patient_shown(a),
                            "time": "Walk-in" if a.source == "walk_in" else self.time(a),
                        }
                        for a in mine
                    ],
                }
            )
        context = {
            **self.admin_site.each_context(request),
            "title": "OPD queue",
            "form": form,
            "walk_in": walk_in,
            "doctors": doctors,
            "shown": data is not None,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/scheduling/appointment/queue.html", context)
