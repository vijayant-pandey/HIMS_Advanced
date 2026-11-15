from rest_framework import serializers

from ..availability import OFF_KINDS
from ..models import (
    MAX_EXTRA_BOOKINGS,
    MAX_SLOT_MINUTES,
    MIN_SLOT_MINUTES,
    DoctorSchedule,
    ScheduleException,
)

SESSION_STATUSES = (
    ("open", "Open"),
    ("partly_off", "Partly off"),
    ("off", "Off"),
)
SESSION_SOURCES = (
    ("weekly", "Weekly session"),
    ("extra", "Extra session"),
)


def _clock(value) -> str:
    return f"{value:%H:%M}" if value else ""


class DoctorScheduleSerializer(serializers.ModelSerializer):
    staff_id = serializers.UUIDField(read_only=True)
    staff_name = serializers.SerializerMethodField()
    department_id = serializers.UUIDField(read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    facility_id = serializers.UUIDField(read_only=True)
    weekday_label = serializers.CharField(source="get_weekday_display", read_only=True)
    hours = serializers.SerializerMethodField(help_text="e.g. 09:00-13:00, on the facility's clock")

    class Meta:
        model = DoctorSchedule
        fields = [
            "id",
            "staff_id",
            "staff_name",
            "department_id",
            "department_name",
            "facility_id",
            "weekday",
            "weekday_label",
            "start_time",
            "end_time",
            "hours",
            "slot_minutes",
            "extra_bookings_allowed",
            "valid_from",
            "valid_until",
            "is_active",
            "note",
            "end_reason",
            "version",
        ]
        read_only_fields = fields

    def get_staff_name(self, schedule) -> str:
        return f"{schedule.staff.given_name} {schedule.staff.family_name}"

    def get_hours(self, schedule) -> str:
        return f"{_clock(schedule.start_time)}-{_clock(schedule.end_time)}"


class AddSessionsSerializer(serializers.Serializer):
    staff = serializers.UUIDField(help_text="The doctor")
    department = serializers.UUIDField()
    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        min_length=1,
        help_text="0 = Monday … 6 = Sunday; one session is added per weekday",
    )
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    slot_minutes = serializers.IntegerField(
        min_value=MIN_SLOT_MINUTES, max_value=MAX_SLOT_MINUTES, default=10
    )
    extra_bookings_allowed = serializers.IntegerField(
        min_value=0, max_value=MAX_EXTRA_BOOKINGS, default=0
    )
    valid_from = serializers.DateField()
    valid_until = serializers.DateField(required=False, allow_null=True, default=None)
    note = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")


class ChangeSessionSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    slot_minutes = serializers.IntegerField(
        min_value=MIN_SLOT_MINUTES, max_value=MAX_SLOT_MINUTES, required=False
    )
    extra_bookings_allowed = serializers.IntegerField(
        min_value=0, max_value=MAX_EXTRA_BOOKINGS, required=False
    )
    note = serializers.CharField(max_length=120, required=False, allow_blank=True)


class EndSessionSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    last_day = serializers.DateField(
        help_text="The last day it runs; before its first day withdraws it"
    )
    reason = serializers.CharField(max_length=255)


class ScheduleExceptionSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    staff_id = serializers.UUIDField(read_only=True, allow_null=True)
    staff_name = serializers.SerializerMethodField()
    facility_id = serializers.UUIDField(read_only=True)
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    department_id = serializers.UUIDField(read_only=True, allow_null=True)
    department_name = serializers.SerializerMethodField()
    hours = serializers.SerializerMethodField(help_text="Empty = the whole day")
    reason = serializers.SerializerMethodField(
        help_text="Why. A doctor's away note is shown only to people who keep the schedules"
    )

    class Meta:
        model = ScheduleException
        fields = [
            "id",
            "kind",
            "kind_label",
            "staff_id",
            "staff_name",
            "facility_id",
            "facility_name",
            "department_id",
            "department_name",
            "start_date",
            "end_date",
            "start_time",
            "end_time",
            "hours",
            "slot_minutes",
            "extra_bookings_allowed",
            "reason",
            "status",
            "cancel_reason",
            "version",
        ]
        read_only_fields = fields

    def get_staff_name(self, item) -> str:
        return f"{item.staff.given_name} {item.staff.family_name}" if item.staff_id else ""

    def get_department_name(self, item) -> str:
        return item.department.name if item.department_id else ""

    def get_hours(self, item) -> str:
        if item.start_time is None:
            return ""
        return f"{_clock(item.start_time)}-{_clock(item.end_time)}"

    def get_reason(self, item) -> str:
        scope = self.context.get("manage_scope")
        if item.kind != ScheduleException.Kind.LEAVE or scope is None:
            return item.reason
        if scope.covers(facility_id=item.facility_id, department_id=item.department_id):
            return item.reason
        return ""  # a doctor's away note is for the people keeping the schedules


class AddExceptionSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=ScheduleException.Kind.choices)
    facility = serializers.UUIDField(
        required=False, help_text="Holiday: the facility (default: the department's)"
    )
    department = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Leave and extra session: required. Holiday: empty = the whole facility",
    )
    staff = serializers.UUIDField(
        required=False, allow_null=True, help_text="The doctor (leave, extra session)"
    )
    start_date = serializers.DateField()
    end_date = serializers.DateField(required=False, allow_null=True, help_text="Default: one day")
    start_time = serializers.TimeField(required=False, allow_null=True, help_text="Empty = all day")
    end_time = serializers.TimeField(required=False, allow_null=True)
    slot_minutes = serializers.IntegerField(
        min_value=MIN_SLOT_MINUTES, max_value=MAX_SLOT_MINUTES, required=False, allow_null=True
    )
    extra_bookings_allowed = serializers.IntegerField(
        min_value=0, max_value=MAX_EXTRA_BOOKINGS, required=False, allow_null=True
    )
    reason = serializers.CharField(max_length=255, help_text="No medical details.")


class CancelExceptionSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    reason = serializers.CharField(max_length=255)


class OffPartSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=OFF_KINDS)
    hours = serializers.CharField(help_text="The part taken off, e.g. 11:00-13:00")
    reason = serializers.CharField()
    exception_id = serializers.UUIDField(allow_null=True)


class SlotSerializer(serializers.Serializer):
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    time = serializers.CharField(help_text="Start, on the facility's clock")
    is_past = serializers.BooleanField()


class SessionSerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=SESSION_SOURCES)
    schedule_id = serializers.UUIDField(allow_null=True)
    exception_id = serializers.UUIDField(allow_null=True)
    staff_id = serializers.UUIDField()
    department_id = serializers.UUIDField()
    department_name = serializers.CharField()
    facility_id = serializers.UUIDField()
    day = serializers.DateField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    hours = serializers.CharField()
    slot_minutes = serializers.IntegerField()
    extra_bookings_allowed = serializers.IntegerField()
    note = serializers.CharField(allow_blank=True)
    status = serializers.ChoiceField(choices=SESSION_STATUSES)
    open_slots = serializers.IntegerField()
    off = OffPartSerializer(many=True)
    slots = SlotSerializer(many=True, help_text="Open slots (only for one doctor's day)")


class SessionDaySerializer(serializers.Serializer):
    day = serializers.DateField()
    leave_asked = serializers.BooleanField(
        help_text="Leave is asked for on the Leave page and not decided yet"
    )
    sessions = SessionSerializer(many=True)


class WeekDoctorSerializer(serializers.Serializer):
    staff_id = serializers.UUIDField()
    name = serializers.CharField()
    designation = serializers.CharField(allow_null=True)
    weekly = DoctorScheduleSerializer(many=True)
    days = SessionDaySerializer(many=True)


class DepartmentWeekSerializer(serializers.Serializer):
    department_id = serializers.UUIDField()
    department_name = serializers.CharField()
    facility_id = serializers.UUIDField()
    facility_name = serializers.CharField()
    start = serializers.DateField()
    days = serializers.ListField(child=serializers.DateField())
    doctors = WeekDoctorSerializer(many=True)
    exceptions = ScheduleExceptionSerializer(many=True)
    can_manage = serializers.BooleanField()
    can_close_facility = serializers.BooleanField(
        help_text="May record a holiday for the whole facility"
    )
    details = serializers.BooleanField(help_text="Doctors' away notes are shown")


class DoctorDaySerializer(serializers.Serializer):
    staff_id = serializers.UUIDField()
    name = serializers.CharField()
    day = serializers.DateField()
    leave_asked = serializers.BooleanField()
    sessions = SessionSerializer(many=True)


class AddedExceptionSerializer(serializers.Serializer):
    exception = ScheduleExceptionSerializer()
    affected = SessionSerializer(
        many=True, help_text="Sessions it takes off (all or part); booked patients come later"
    )


class MyOpdWeekSerializer(serializers.Serializer):
    has_staff_record = serializers.BooleanField()
    start = serializers.DateField()
    days = SessionDaySerializer(many=True)
