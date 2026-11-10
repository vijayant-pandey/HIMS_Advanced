from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.organizations.dates import hospital_time

from ..models import LeaveRequest, Shift, ShiftType


class ShiftTypeSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    minutes = serializers.IntegerField(read_only=True)

    class Meta:
        model = ShiftType
        fields = [
            "id",
            "code",
            "name",
            "kind",
            "kind_label",
            "start_time",
            "end_time",
            "minutes",
            "is_active",
            "is_custom",
            "version",
        ]
        read_only_fields = fields


class ShiftTypeCreateSerializer(serializers.Serializer):
    code = serializers.SlugField(max_length=32)
    name = serializers.CharField(max_length=64)
    kind = serializers.ChoiceField(choices=ShiftType.Kind.choices)
    start_time = serializers.TimeField()
    end_time = serializers.TimeField(help_text="At or before the start = ends the next day")


class ShiftTypeUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    name = serializers.CharField(max_length=64, required=False)
    kind = serializers.ChoiceField(choices=ShiftType.Kind.choices, required=False)
    start_time = serializers.TimeField(required=False)
    end_time = serializers.TimeField(required=False)
    is_active = serializers.BooleanField(required=False)


class ShiftSerializer(serializers.ModelSerializer):
    staff_id = serializers.UUIDField(read_only=True)
    staff_name = serializers.SerializerMethodField()
    department_id = serializers.UUIDField(read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    facility_id = serializers.UUIDField(read_only=True)
    shift_type_id = serializers.UUIDField(read_only=True)
    shift_type_name = serializers.CharField(source="shift_type.name", read_only=True)
    kind = serializers.ChoiceField(
        source="shift_type.kind", choices=ShiftType.Kind.choices, read_only=True
    )
    hours = serializers.SerializerMethodField(help_text="e.g. 20:00-08:00, on the facility's clock")

    class Meta:
        model = Shift
        fields = [
            "id",
            "staff_id",
            "staff_name",
            "department_id",
            "department_name",
            "facility_id",
            "shift_type_id",
            "shift_type_name",
            "kind",
            "on_date",
            "starts_at",
            "ends_at",
            "hours",
            "note",
            "status",
            "cancel_reason",
            "version",
        ]
        read_only_fields = fields

    def get_staff_name(self, shift) -> str:
        return f"{shift.staff.given_name} {shift.staff.family_name}"

    def get_hours(self, shift) -> str:
        start = hospital_time(shift.starts_at, shift.facility)
        end = hospital_time(shift.ends_at, shift.facility)
        return f"{start:%H:%M}-{end:%H:%M}"


class AddShiftsSerializer(serializers.Serializer):
    staff = serializers.UUIDField()
    department = serializers.UUIDField()
    shift_type = serializers.UUIDField()
    from_date = serializers.DateField()
    to_date = serializers.DateField(required=False, help_text="Default: the same day")
    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        required=False,
        help_text="Only these weekdays (0 = Monday … 6 = Sunday); default every day",
    )
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class SkippedDaySerializer(serializers.Serializer):
    on_date = serializers.DateField()
    person = serializers.CharField()
    reason = serializers.CharField()


class AddShiftsResultSerializer(serializers.Serializer):
    created = ShiftSerializer(many=True)
    skipped = SkippedDaySerializer(many=True)


class CopyWeekSerializer(serializers.Serializer):
    department = serializers.UUIDField()
    from_start = serializers.DateField(help_text="First day of the week to copy")
    to_start = serializers.DateField(help_text="First day of the week to fill (a later week)")


class CancelSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    reason = serializers.CharField(max_length=255)


class RotaAwaySerializer(serializers.Serializer):
    leave_id = serializers.UUIDField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    status = serializers.ChoiceField(choices=LeaveRequest.Status.choices)
    leave_type = serializers.CharField(
        allow_null=True, help_text="Only for people who decide leave"
    )
    leave_type_label = serializers.CharField(allow_null=True)


class RotaPersonSerializer(serializers.Serializer):
    staff_id = serializers.UUIDField()
    name = serializers.CharField()
    designation = serializers.CharField(allow_null=True)
    shifts = ShiftSerializer(many=True)
    away = RotaAwaySerializer(many=True)


class StaffingGapSerializer(serializers.Serializer):
    on_date = serializers.DateField()
    shift_type_id = serializers.UUIDField()
    shift_type_name = serializers.CharField()
    staff_type = serializers.CharField()
    staff_type_label = serializers.CharField()
    minimum = serializers.IntegerField()
    planned = serializers.IntegerField()
    short_by = serializers.IntegerField()


class RotaWeekSerializer(serializers.Serializer):
    department_id = serializers.UUIDField()
    department_name = serializers.CharField()
    facility_id = serializers.UUIDField()
    facility_name = serializers.CharField()
    start = serializers.DateField()
    days = serializers.ListField(child=serializers.DateField())
    can_manage = serializers.BooleanField()
    leave_details = serializers.BooleanField()
    people = RotaPersonSerializer(many=True)
    staffing_gaps = StaffingGapSerializer(many=True)


class RotaNowSerializer(serializers.Serializer):
    at = serializers.DateTimeField()
    on_call = ShiftSerializer(many=True)
    working = ShiftSerializer(many=True)


class LeaveRequestSerializer(serializers.ModelSerializer):
    staff_id = serializers.UUIDField(read_only=True)
    staff_name = serializers.SerializerMethodField()
    department_id = serializers.UUIDField(read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    facility_id = serializers.UUIDField(read_only=True)
    leave_type_label = serializers.CharField(source="get_leave_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    days = serializers.IntegerField(read_only=True)
    requested_by_name = serializers.CharField(
        source="requested_by.display_name", read_only=True, default=None, allow_null=True
    )
    decided_by_name = serializers.CharField(
        source="decided_by.display_name", read_only=True, default=None, allow_null=True
    )
    balance_after = serializers.SerializerMethodField()
    conflicting_shifts = serializers.SerializerMethodField(
        help_text="Planned shifts the person would miss (only while waiting for a decision)"
    )

    class Meta:
        model = LeaveRequest
        fields = [
            "id",
            "staff_id",
            "staff_name",
            "department_id",
            "department_name",
            "facility_id",
            "leave_type",
            "leave_type_label",
            "start_date",
            "end_date",
            "days",
            "reason",
            "status",
            "status_label",
            "requested_by_name",
            "created_at",
            "decided_by_name",
            "decided_at",
            "decision_note",
            "cancelled_at",
            "cancel_reason",
            "conflicting_shifts",
            "balance_after",
            "version",
        ]
        read_only_fields = fields

    def get_staff_name(self, leave) -> str:
        return f"{leave.staff.given_name} {leave.staff.family_name}"

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_balance_after(self, leave):
        """What would be left if approved; empty when decided, or not a tracked kind of leave."""
        from ..balances import balance_after

        return balance_after(leave) if leave.status == LeaveRequest.Status.REQUESTED else None

    @extend_schema_field(ShiftSerializer(many=True))
    def get_conflicting_shifts(self, leave):
        from ..services import conflicting_shifts

        if leave.status != LeaveRequest.Status.REQUESTED:
            return []
        return ShiftSerializer(conflicting_shifts(leave), many=True).data


class LeaveCreateSerializer(serializers.Serializer):
    staff = serializers.UUIDField(required=False, help_text="Approvers only: whose leave")
    department = serializers.UUIDField()
    leave_type = serializers.ChoiceField(choices=LeaveRequest.LeaveType.choices)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    reason = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        default="",
        help_text="Optional. No medical details: the kind of leave is enough",
    )


class LeaveDecisionSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    cancel_shifts = serializers.BooleanField(
        required=False, default=False, help_text="Approve: also cancel shifts during the leave"
    )
    allow_over_balance = serializers.BooleanField(
        required=False, default=False, help_text="Approve even if it goes over the balance"
    )


class MyPostingSerializer(serializers.Serializer):
    department_id = serializers.UUIDField()
    department_name = serializers.CharField()
    facility_name = serializers.CharField()
    is_primary = serializers.BooleanField()


class LeaveBalanceSerializer(serializers.Serializer):
    leave_type = serializers.CharField()
    label = serializers.CharField()
    year = serializers.IntegerField()
    year_label = serializers.CharField()
    entitled = serializers.IntegerField()
    carried_in = serializers.IntegerField()
    adjusted = serializers.IntegerField()
    taken = serializers.IntegerField()
    waiting = serializers.IntegerField(help_text="Asked for, not decided yet: not taken off")
    remaining = serializers.IntegerField()


class MyScheduleSerializer(serializers.Serializer):
    has_staff_record = serializers.BooleanField()
    name = serializers.CharField(required=False)
    postings = MyPostingSerializer(many=True)
    shifts = ShiftSerializer(many=True)
    leave = LeaveRequestSerializer(many=True)
    leave_balances = LeaveBalanceSerializer(many=True)
