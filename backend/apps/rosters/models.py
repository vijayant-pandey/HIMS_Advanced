"""Shift schedules, on-call rotations and leave (spec 4.3; HIMS-STAFF-012).

A shift is one person working (or on call) in one department, from a start to an end instant.
The instants are worked out once, from the day and the shift type's clock times in the
facility's time zone, and stored; later edits to a shift type do not move planned shifts.

The database refuses overlapping shifts for one person and overlapping leave for one person
(exclusion constraints, spec 10), so two planners working at once cannot double-book anyone.
"""

from datetime import date, datetime, timedelta

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, DateTimeRangeField, RangeOperators
from django.db import models
from django.db.models import F, Func, Q

from common.models import (
    OrganizationOwnedModel,
    TimeStampedModel,
    UUIDPrimaryKeyModel,
    VersionedModel,
)


class TsTzRange(Func):
    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class DateRange(Func):
    function = "DATERANGE"
    output_field = DateRangeField()


class ShiftType(UUIDPrimaryKeyModel, TimeStampedModel, VersionedModel):
    """A kind of shift the hospital uses, e.g. Morning 08:00-14:00 or On call 24 hours.

    Clock times are in the facility's time zone. An end at or before the start means the shift
    ends the next day (a night shift); equal times mean 24 hours."""

    class Kind(models.TextChoices):
        SHIFT = "shift", "Working shift"
        ON_CALL = "on_call", "On call"

    code = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=64)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.SHIFT)
    start_time = models.TimeField(help_text="Start, on the facility's clock")
    end_time = models.TimeField(help_text="End; at or before the start means it ends the next day")
    is_active = models.BooleanField(default=True)
    is_custom = models.BooleanField(
        default=False, help_text="Added by this hospital (standard entries come with HIMS)."
    )

    class Meta:
        db_table = "shift_types"
        ordering = ["kind", "start_time", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.start_time:%H:%M}-{self.end_time:%H:%M})"

    @property
    def minutes(self) -> int:
        start = self.start_time.hour * 60 + self.start_time.minute
        end = self.end_time.hour * 60 + self.end_time.minute
        return (end - start) % (24 * 60) or 24 * 60

    def window(self, on_date: date, zone) -> tuple[datetime, datetime]:
        """Start and end instants of this shift on a day, on a facility's clock."""
        start = datetime.combine(on_date, self.start_time, tzinfo=zone)
        end_day = on_date if self.end_time > self.start_time else on_date + timedelta(days=1)
        return start, datetime.combine(end_day, self.end_time, tzinfo=zone)


class Shift(OrganizationOwnedModel, VersionedModel):
    """One person on one shift, or on call, in one department, starting on one day."""

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CANCELLED = "cancelled", "Cancelled"

    staff = models.ForeignKey("staff.StaffMember", on_delete=models.PROTECT, related_name="shifts")
    facility = models.ForeignKey("facilities.Facility", on_delete=models.PROTECT, related_name="+")
    department = models.ForeignKey(
        "facilities.Department", on_delete=models.PROTECT, related_name="shifts"
    )
    shift_type = models.ForeignKey(ShiftType, on_delete=models.PROTECT, related_name="+")
    on_date = models.DateField(help_text="Day the shift starts, at the facility")
    starts_at = models.DateTimeField(help_text="Worked out from the day and the shift type")
    ends_at = models.DateTimeField(help_text="Worked out from the day and the shift type")
    note = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SCHEDULED)
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
        db_table = "shifts"
        ordering = ["starts_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")), name="shift_ends_after_start"
            ),
            ExclusionConstraint(
                name="shift_no_overlap_per_person",
                expressions=[
                    ("staff", RangeOperators.EQUAL),
                    (TsTzRange("starts_at", "ends_at"), RangeOperators.OVERLAPS),
                ],
                condition=Q(status="scheduled"),
                violation_error_message="One person cannot have two shifts at the same time.",
            ),
        ]
        indexes = [
            models.Index(fields=["department", "on_date"], name="shift_department_day_idx"),
            models.Index(fields=["staff", "on_date"], name="shift_staff_day_idx"),
            models.Index(fields=["starts_at", "ends_at"], name="shift_time_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.staff} - {self.shift_type.name} on {self.on_date:%d %b %Y}"


class LeaveRequest(OrganizationOwnedModel, VersionedModel):
    """Time away asked for by a staff member (or recorded for them), and its decision."""

    class LeaveType(models.TextChoices):
        ANNUAL = "annual", "Annual / earned leave"
        CASUAL = "casual", "Casual leave"
        SICK = "sick", "Sick leave"
        MATERNITY = "maternity", "Maternity leave"
        PATERNITY = "paternity", "Paternity leave"
        STUDY = "study", "Study or conference leave"
        COMPENSATORY = "compensatory", "Compensatory off"
        UNPAID = "unpaid", "Unpaid leave"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        REQUESTED = "requested", "Waiting for a decision"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Refused"
        CANCELLED = "cancelled", "Cancelled"

    staff = models.ForeignKey(
        "staff.StaffMember", on_delete=models.PROTECT, related_name="leave_requests"
    )
    facility = models.ForeignKey("facilities.Facility", on_delete=models.PROTECT, related_name="+")
    department = models.ForeignKey(
        "facilities.Department",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Where the person is posted; its approvers decide",
    )
    leave_type = models.CharField(max_length=16, choices=LeaveType.choices)
    start_date = models.DateField()
    end_date = models.DateField(help_text="Last day of leave (inclusive)")
    reason = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.REQUESTED)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    decision_note = models.CharField(max_length=500, blank=True)
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
        db_table = "leave_requests"
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")), name="leave_ends_after_start"
            ),
            ExclusionConstraint(
                name="leave_no_overlap_per_person",
                expressions=[
                    ("staff", RangeOperators.EQUAL),
                    (
                        DateRange("start_date", "end_date", models.Value("[]")),
                        RangeOperators.OVERLAPS,
                    ),
                ],
                condition=Q(status__in=["requested", "approved"]),
                violation_error_message="This person already has leave asked for or approved "
                "on some of these days.",
            ),
        ]
        indexes = [
            models.Index(fields=["department", "status"], name="leave_department_status_idx"),
            models.Index(fields=["staff", "start_date"], name="leave_staff_start_idx"),
        ]

    def __str__(self) -> str:
        period = f"{self.start_date:%d %b}-{self.end_date:%d %b %Y}"
        return f"{self.staff} - {self.get_leave_type_display()} {period}"

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1
