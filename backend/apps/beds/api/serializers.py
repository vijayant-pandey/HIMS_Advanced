from rest_framework import serializers

from apps.facilities.models import Room

from ..models import Bed


class BedSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bed
        fields = [
            "id",
            "facility",
            "ward",
            "room",
            "code",
            "bed_type",
            "status",
            "status_reason",
            "status_changed_at",
            "is_active",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class BedCreateSerializer(serializers.ModelSerializer):
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all())

    class Meta:
        model = Bed
        fields = ["room", "code", "bed_type"]
        validators = []  # uniqueness is checked by the model (clear message, 400)


class BedUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    bed_type = serializers.ChoiceField(Bed.BedType.choices, required=False)
    is_active = serializers.BooleanField(required=False)


class BedStatusChangeSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    status = serializers.ChoiceField(
        choices=[(s.value, s.label) for s in Bed.Status if s in Bed.OPERATIONAL_STATES]
    )
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class BulkBedsSerializer(serializers.Serializer):
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all())
    prefix = serializers.SlugField(max_length=10, help_text="e.g. 'B' gives B01, B02, …")
    start = serializers.IntegerField(min_value=0, max_value=9999, default=1)
    count = serializers.IntegerField(min_value=1, max_value=60)
    bed_type = serializers.ChoiceField(Bed.BedType.choices)


# --- Facility location tree (one request for the whole structure) --------------------------


class TreeBedSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    bed_type = serializers.CharField()
    status = serializers.CharField()
    status_reason = serializers.CharField()
    is_active = serializers.BooleanField()
    version = serializers.IntegerField()


class TreeRoomSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    room_type = serializers.CharField()
    is_isolation_capable = serializers.BooleanField()
    is_active = serializers.BooleanField()
    version = serializers.IntegerField()
    beds = TreeBedSerializer(many=True)


class TreeWardSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    ward_type = serializers.CharField()
    department = serializers.UUIDField(allow_null=True)
    department_name = serializers.CharField(allow_null=True)
    gender_restriction = serializers.CharField()
    age_group = serializers.CharField()
    is_active = serializers.BooleanField()
    version = serializers.IntegerField()
    bed_counts = serializers.DictField(child=serializers.IntegerField(), help_text="by status")
    rooms = TreeRoomSerializer(many=True)


class TreeFloorSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    level = serializers.IntegerField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()
    version = serializers.IntegerField()
    wards = TreeWardSerializer(many=True)


class TreeBuildingSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()
    version = serializers.IntegerField()
    floors = TreeFloorSerializer(many=True)


class FacilityLocationsSerializer(serializers.Serializer):
    facility = serializers.UUIDField()
    bed_counts = serializers.DictField(child=serializers.IntegerField(), help_text="by status")
    buildings = TreeBuildingSerializer(many=True)
