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

**Appointments** (HIMS-OPD-002) book patients into those slots. The database refuses two
appointments of one doctor at the same time (exclusion constraint), so two receptionists booking
the same slot at the same moment cannot both succeed (P0 part 01 section 10).
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


class TimeRange(Func):
    """An appointment's time as a range, so PostgreSQL can refuse two that overlap."""

    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class Appointment(OrganizationOwnedModel, VersionedModel):
    """A patient booked into a slot of a doctor's OPD session (HIMS-OPD-002; P0 part 02).

    The slot comes from a weekly session or an extra session on that day. Two appointments of one
    doctor never overlap (exclusion constraint), except bookings over the slots that the session
    allows (``is_extra``, D11), which are counted per session under a lock on the doctor. Nothing
    is deleted: a cancelled appointment keeps who, when and why, and a moved one links to the
    appointment that replaced it.

    The day of the visit (HIMS-OPD-003; P0 part 01 section 4, D10, D12): a patient checked in gets
    the doctor's next token number for the day; a walk-in is checked in at once without a slot
    (``source`` walk-in: it takes no slot, so the no-double-booking rule leaves it out). Booked
    patients not checked in when their session ends are marked "did not come" by a job.
    """

    class Kind(models.TextChoices):
        NEW = "new", "New"
        FOLLOW_UP = "follow_up", "Follow-up"

    class Source(models.TextChoices):
        FRONT_DESK = "front_desk", "At the front desk"
        PHONE = "phone", "By phone"
        WALK_IN = "walk_in", "Walk-in"

    class Status(models.TextChoices):
        BOOKED = "booked", "Booked"
        CHECKED_IN = "checked_in", "Checked in"
        IN_CONSULTATION = "in_consultation", "With the doctor"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "Did not come"

    class CancelReason(models.TextChoices):
        PATIENT_REQUEST = "patient_request", "The patient asked"
        HOSPITAL = "hospital", "The hospital cancelled"
        DOCTOR_UNAVAILABLE = "doctor_unavailable", "The doctor is not available"
        RESCHEDULED = "rescheduled", "Moved to another time"
        LEFT_UNSEEN = "left_unseen", "Left before being seen"

    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="appointments", db_index=False
    )
    staff = models.ForeignKey(
        "staff.StaffMember",
        on_delete=models.PROTECT,
        related_name="appointments",
        db_index=False,
        help_text="The doctor",
    )
    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.PROTECT, related_name="+", db_index=False
    )
    department = models.ForeignKey(
        "facilities.Department", on_delete=models.PROTECT, related_name="+", db_index=False
    )
    schedule = models.ForeignKey(
        DoctorSchedule,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="appointments",
        help_text="The weekly session (empty for an extra session)",
    )
    extra_session = models.ForeignKey(
        ScheduleException,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="appointments",
        db_index=False,
        help_text="The extra session (empty for a weekly session)",
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    local_date = models.DateField(help_text="The day on the facility's clock")
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.NEW)
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.FRONT_DESK)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.BOOKED)
    reason = models.CharField(
        max_length=200, blank=True, help_text="Short reason for the visit. No detailed history."
    )
    is_extra = models.BooleanField(
        default=False, help_text="Booked over the session's slots (extra bookings, D11)"
    )
    rescheduled_from = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="rescheduled_to",
        help_text="The appointment this one replaced",
    )
    booked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        related_name="+",
        db_index=False,
    )
    cancel_reason = models.CharField(max_length=24, choices=CancelReason.choices, blank=True)
    cancel_note = models.CharField(max_length=255, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_index=False,
    )
    # The day of the visit (HIMS-OPD-003).
    token_number = models.PositiveIntegerField(
        null=True, blank=True, help_text="The doctor's token for the day, given at check-in"
    )
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_in_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_index=False,
    )
    called_at = models.DateTimeField(
        null=True, blank=True, help_text="When the patient was called in to the doctor"
    )
    seen_at = models.DateTimeField(null=True, blank=True, help_text="When the doctor was done")

    class Meta:
        db_table = "appointments"
        ordering = ["starts_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")), name="appointment_ends_after_start"
            ),
            models.CheckConstraint(
                condition=Q(schedule__isnull=False, extra_session__isnull=True)
                | Q(schedule__isnull=True, extra_session__isnull=False),
                name="appointment_one_session",
            ),
            models.CheckConstraint(
                # Cancelled with when and why, or not cancelled and nothing of either.
                condition=(Q(status="cancelled", cancelled_at__isnull=False) & ~Q(cancel_reason=""))
                | (Q(cancelled_at__isnull=True, cancel_reason="") & ~Q(status="cancelled")),
                name="appointment_cancelled",
            ),
            models.CheckConstraint(
                condition=Q(rescheduled_from__isnull=True) | ~Q(rescheduled_from=F("id")),
                name="appointment_not_moved_to_itself",
            ),
            ExclusionConstraint(
                name="appointment_no_double_booking",
                expressions=[
                    ("staff", RangeOperators.EQUAL),
                    (TimeRange("starts_at", "ends_at"), RangeOperators.OVERLAPS),
                ],
                # A walk-in takes no slot (HIMS-OPD-003): it waits for its token.
                condition=Q(status__in=["booked", "checked_in", "in_consultation"], is_extra=False)
                & ~Q(source="walk_in"),
                violation_error_message="This slot was just taken.",
            ),
            # One token number per doctor and day (P0 part 02; given under the doctor's lock).
            models.UniqueConstraint(
                fields=["staff", "local_date", "token_number"],
                condition=Q(token_number__isnull=False),
                name="appointment_one_token",
            ),
            models.CheckConstraint(
                # Checked in (waiting, with the doctor, seen) means a token and when; booked or
                # did not come means neither; leaving before being seen keeps them.
                condition=(
                    Q(token_number__isnull=True, checked_in_at__isnull=True)
                    & Q(status__in=["booked", "no_show", "cancelled"])
                )
                | (
                    Q(token_number__isnull=False, checked_in_at__isnull=False)
                    & Q(status__in=["checked_in", "in_consultation", "completed", "cancelled"])
                ),
                name="appointment_checked_in",
            ),
            models.CheckConstraint(
                # With the doctor or seen means called in first; seen means when.
                condition=(
                    Q(called_at__isnull=False) | ~Q(status__in=["in_consultation", "completed"])
                )
                & (Q(seen_at__isnull=False) | ~Q(status="completed")),
                name="appointment_called_and_seen",
            ),
            models.CheckConstraint(
                # A walk-in is checked in at once and is never over the slots.
                condition=~Q(source="walk_in") | Q(token_number__isnull=False, is_extra=False),
                name="appointment_walk_in",
            ),
        ]
        indexes = [
            models.Index(fields=["staff", "local_date"], name="appointment_staff_day_idx"),
            models.Index(fields=["patient", "starts_at"], name="appointment_patient_idx"),
            # The console's list, newest first (the volume check measured 2.4 s without it).
            models.Index(fields=["-starts_at"], name="appointment_start_idx"),
            # The "To move" list: booked appointments in a department (small: booked only).
            # The OPD queue reads a department's doctors' day through appointment_staff_day_idx
            # (HIMS-OPD-003), so P0's facility day index is not needed (ADR-040).
            models.Index(
                fields=["department", "starts_at"],
                condition=Q(status="booked"),
                name="appointment_booked_dept_idx",
            ),
            # The no-show job: booked appointments whose slot has ended (HIMS-OPD-003). On the end,
            # not the start, so the To move list (booked ones still to come) never reads it.
            models.Index(
                fields=["ends_at"],
                condition=Q(status="booked"),
                name="appointment_booked_end_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.patient} with {self.staff}, {self.local_date:%d %b %Y}"

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES


# An appointment that holds its slot (P0 part 02: the exclusion constraint's condition).
ACTIVE_STATUSES = (
    Appointment.Status.BOOKED,
    Appointment.Status.CHECKED_IN,
    Appointment.Status.IN_CONSULTATION,
)
