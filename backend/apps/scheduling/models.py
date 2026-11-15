"""Doctor OPD schedules and their exceptions (spec 4.6; HIMS-OPD-001; P0 part 02).

A **session** is a doctor seeing outpatients in one department on one weekday, e.g. every Monday
09:00-13:00 in Cardiology, cut into slots (10 minutes by default) for appointments (HIMS-OPD-002).
Clock times are on the facility's clock. An **exception** changes the weekly pattern: the doctor
is away (leave), the facility or one department is closed (holiday), or the doctor holds an extra
session on one day.

Approved leave on the Leave page (the step 1 rotas, HIMS-STAFF-012) also takes the doctor's
sessions off, without being entered twice. Nothing here is deleted: sessions are ended and
exceptions cancelled, each with who, when and why. The database refuses two weekly sessions of one
doctor at the same time (exclusion constraint), so two schedulers working at once cannot overlap
them. See docs/architecture/data-architecture/scheduling.md.
"""

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db import models
from django.db.models import F, Func, Q

from apps.facilities.models import DepartmentHours
from apps.rosters.models import DateRange
from common.models import OrganizationOwnedModel, VersionedModel

MIN_SLOT_MINUTES, MAX_SLOT_MINUTES = 5, 120
MAX_EXTRA_BOOKINGS = 20  # D11: up to N bookings over the slots, per session


class ClockRange(Func):
    """Two clock times as a range on one fixed day, so PostgreSQL can compare sessions' hours
    (only the times matter; DATE + TIME is immutable, which an exclusion constraint needs)."""

    function = "TSRANGE"
    template = "%(function)s(DATE '2000-01-03' + %(expressions)s)"
    arg_joiner = ", DATE '2000-01-03' + "
    output_field = DateTimeRangeField()


class DoctorSchedule(OrganizationOwnedModel, VersionedModel):
    """One weekly OPD session of one doctor in one department, valid from a day (until a day)."""

    staff = models.ForeignKey(
        "staff.StaffMember", on_delete=models.PROTECT, related_name="opd_schedules"
    )
    facility = models.ForeignKey("facilities.Facility", on_delete=models.PROTECT, related_name="+")
    department = models.ForeignKey(
        "facilities.Department", on_delete=models.PROTECT, related_name="opd_schedules"
    )
    weekday = models.PositiveSmallIntegerField(choices=DepartmentHours.Weekday.choices)
    start_time = models.TimeField(help_text="On the facility's clock")
    end_time = models.TimeField(help_text="On the facility's clock, the same day")
    slot_minutes = models.PositiveSmallIntegerField(
        default=10, help_text="Length of one appointment slot"
    )
    extra_bookings_allowed = models.PositiveSmallIntegerField(
        default=0, help_text="Bookings allowed over the slots in one session (0 = none)"
    )
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True, help_text="Last day; empty = no end")
    is_active = models.BooleanField(
        default=True, help_text="Off: withdrawn before its first day (it never ran)"
    )
    note = models.CharField(
        max_length=120, blank=True, help_text="e.g. Room 4. No patient details."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="+"
    )
    ended_at = models.DateTimeField(null=True, blank=True)
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    end_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "doctor_schedules"
        ordering = ["weekday", "start_time"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_time__gt=F("start_time")), name="doctor_schedule_ends_after_start"
            ),
            models.CheckConstraint(
                condition=Q(weekday__gte=0, weekday__lte=6), name="doctor_schedule_weekday"
            ),
            models.CheckConstraint(
                condition=Q(slot_minutes__gte=MIN_SLOT_MINUTES, slot_minutes__lte=MAX_SLOT_MINUTES),
                name="doctor_schedule_slot_minutes",
            ),
            models.CheckConstraint(
                condition=Q(extra_bookings_allowed__lte=MAX_EXTRA_BOOKINGS),
                name="doctor_schedule_extra_bookings",
            ),
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True) | Q(valid_until__gte=F("valid_from")),
                name="doctor_schedule_valid_dates",
            ),
            ExclusionConstraint(
                name="doctor_schedule_no_overlap",
                expressions=[
                    ("staff", RangeOperators.EQUAL),
                    ("weekday", RangeOperators.EQUAL),
                    (
                        DateRange("valid_from", "valid_until", models.Value("[]")),
                        RangeOperators.OVERLAPS,
                    ),
                    (ClockRange("start_time", "end_time"), RangeOperators.OVERLAPS),
                ],
                condition=Q(is_active=True),
                violation_error_message="This doctor already has an OPD session at that time.",
            ),
        ]
        indexes = [
            models.Index(fields=["staff", "weekday"], name="doctor_schedule_staff_idx"),
        ]

    def __str__(self) -> str:
        day = DepartmentHours.Weekday(self.weekday).label
        return f"{self.staff} - {day} {self.start_time:%H:%M}-{self.end_time:%H:%M}"


class ScheduleException(OrganizationOwnedModel, VersionedModel):
    """A change to the weekly sessions: a doctor away, a facility or department closed, or one
    extra session. Leave and holidays may cover several days, or part of one day."""

    class Kind(models.TextChoices):
        LEAVE = "leave", "Doctor away (OPD leave)"
        HOLIDAY = "holiday", "Holiday (OPD closed)"
        EXTRA_SESSION = "extra_session", "Extra session"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    staff = models.ForeignKey(
        "staff.StaffMember",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="opd_exceptions",
        help_text="The doctor (leave, extra session); empty for a holiday",
    )
    facility = models.ForeignKey("facilities.Facility", on_delete=models.PROTECT, related_name="+")
    department = models.ForeignKey(
        "facilities.Department",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Leave: the department that recorded it. Holiday: empty = the whole facility",
    )
    start_date = models.DateField()
    end_date = models.DateField(help_text="Last day (inclusive)")
    start_time = models.TimeField(null=True, blank=True, help_text="Empty = the whole day")
    end_time = models.TimeField(null=True, blank=True)
    slot_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    extra_bookings_allowed = models.PositiveSmallIntegerField(null=True, blank=True)
    reason = models.CharField(max_length=255, help_text="No medical details.")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="+"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    cancel_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "schedule_exceptions"
        ordering = ["start_date", "start_time"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")), name="schedule_exception_dates"
            ),
            models.CheckConstraint(
                condition=Q(start_time__isnull=True, end_time__isnull=True)
                | Q(start_time__isnull=False, end_time__isnull=False, end_time__gt=F("start_time")),
                name="schedule_exception_times",
            ),
            models.CheckConstraint(
                condition=Q(start_time__isnull=True) | Q(end_date=F("start_date")),
                name="schedule_exception_times_one_day",
            ),
            models.CheckConstraint(
                condition=Q(kind="holiday", staff__isnull=True)
                | Q(
                    kind__in=["leave", "extra_session"],
                    staff__isnull=False,
                    department__isnull=False,
                ),
                name="schedule_exception_whose",
            ),
            models.CheckConstraint(
                condition=~Q(kind="extra_session")
                | Q(
                    start_time__isnull=False,
                    end_date=F("start_date"),
                    # NULL would pass a CHECK, so "filled in" is checked on its own.
                    slot_minutes__isnull=False,
                    extra_bookings_allowed__isnull=False,
                    slot_minutes__gte=MIN_SLOT_MINUTES,
                    slot_minutes__lte=MAX_SLOT_MINUTES,
                    extra_bookings_allowed__lte=MAX_EXTRA_BOOKINGS,
                ),
                name="schedule_exception_extra_session",
            ),
        ]
        indexes = [
            models.Index(fields=["staff", "start_date"], name="schedule_exception_staff_idx"),
            models.Index(fields=["facility", "start_date"], name="schedule_exception_fac_idx"),
        ]

    def __str__(self) -> str:
        who = self.staff if self.staff_id else (self.department or self.facility)
        period = f"{self.start_date:%d %b %Y}"
        if self.end_date and self.end_date != self.start_date:
            period += f"-{self.end_date:%d %b %Y}"
        return f"{self.get_kind_display()}: {who}, {period}"

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1
