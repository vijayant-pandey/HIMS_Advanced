from rest_framework import serializers

from apps.facilities.models import Department, Facility, Room, Ward

from ..models import Equipment, EquipmentServiceRecord
from ..services import due_state


class EquipmentSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    department_name = serializers.CharField(
        source="department.name", read_only=True, allow_null=True, default=None
    )
    ward_name = serializers.CharField(
        source="ward.name", read_only=True, allow_null=True, default=None
    )
    room_name = serializers.CharField(
        source="room.name", read_only=True, allow_null=True, default=None
    )
    due_state = serializers.SerializerMethodField(help_text='"overdue", "due_soon" or empty')

    def get_due_state(self, item) -> str:
        return due_state(item)

    class Meta:
        model = Equipment
        fields = [
            "id",
            "asset_tag",
            "name",
            "category",
            "category_label",
            "facility",
            "facility_name",
            "department",
            "department_name",
            "ward",
            "ward_name",
            "room",
            "room_name",
            "location_note",
            "manufacturer",
            "model_name",
            "serial_number",
            "status",
            "status_label",
            "status_reason",
            "status_changed_at",
            "purchased_on",
            "warranty_until",
            "last_service_on",
            "next_service_due",
            "last_calibrated_on",
            "next_calibration_due",
            "due_state",
            "notes",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class _EquipmentFields(serializers.Serializer):
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True
    )
    ward = serializers.PrimaryKeyRelatedField(
        queryset=Ward.objects.all(), required=False, allow_null=True
    )
    room = serializers.PrimaryKeyRelatedField(
        queryset=Room.objects.all(), required=False, allow_null=True
    )
    location_note = serializers.CharField(max_length=120, required=False, allow_blank=True)
    category = serializers.ChoiceField(Equipment.Category.choices, required=False)
    manufacturer = serializers.CharField(max_length=120, required=False, allow_blank=True)
    model_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    serial_number = serializers.CharField(max_length=80, required=False, allow_blank=True)
    purchased_on = serializers.DateField(required=False, allow_null=True)
    warranty_until = serializers.DateField(required=False, allow_null=True)
    last_service_on = serializers.DateField(required=False, allow_null=True)
    next_service_due = serializers.DateField(required=False, allow_null=True)
    last_calibrated_on = serializers.DateField(required=False, allow_null=True)
    next_calibration_due = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class EquipmentCreateSerializer(_EquipmentFields):
    facility = serializers.PrimaryKeyRelatedField(queryset=Facility.objects.all())
    asset_tag = serializers.CharField(max_length=40)
    name = serializers.CharField(max_length=120)


class EquipmentUpdateSerializer(_EquipmentFields):
    version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=120, required=False)


class EquipmentStatusSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    status = serializers.ChoiceField(Equipment.Status.choices)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class ServiceRecordCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(EquipmentServiceRecord.Kind.choices)
    performed_on = serializers.DateField()
    performed_by = serializers.CharField(max_length=120, required=False, allow_blank=True)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)
    next_due = serializers.DateField(required=False, allow_null=True)


class ServiceRecordSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    recorded_by_name = serializers.CharField(
        source="recorded_by.display_name", read_only=True, allow_null=True, default=None
    )

    class Meta:
        model = EquipmentServiceRecord
        fields = [
            "id",
            "kind",
            "kind_label",
            "performed_on",
            "performed_by",
            "notes",
            "next_due",
            "recorded_by_name",
            "recorded_at",
        ]
        read_only_fields = fields
