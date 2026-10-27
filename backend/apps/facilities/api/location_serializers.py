from rest_framework import serializers

from ..models import Building, Department, Facility, Floor, Room, Ward

COMMON_READ = ["id", "facility", "is_active", "version", "created_at", "updated_at"]


class BuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Building
        fields = [*COMMON_READ, "code", "name"]
        read_only_fields = fields


class BuildingCreateSerializer(serializers.ModelSerializer):
    facility = serializers.PrimaryKeyRelatedField(queryset=Facility.objects.all())

    class Meta:
        model = Building
        fields = ["facility", "code", "name"]
        validators = []  # uniqueness is checked by the model (clear message, 400)


class BuildingUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=255, required=False)
    is_active = serializers.BooleanField(required=False)


class FloorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Floor
        fields = [*COMMON_READ, "building", "level", "name"]
        read_only_fields = fields


class FloorCreateSerializer(serializers.ModelSerializer):
    building = serializers.PrimaryKeyRelatedField(queryset=Building.objects.all())

    class Meta:
        model = Floor
        fields = ["building", "level", "name"]
        validators = []


class FloorUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=100, required=False)
    level = serializers.IntegerField(min_value=-5, max_value=200, required=False)
    is_active = serializers.BooleanField(required=False)


class WardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ward
        fields = [
            *COMMON_READ,
            "floor",
            "department",
            "code",
            "name",
            "ward_type",
            "gender_restriction",
            "age_group",
        ]
        read_only_fields = fields


class WardCreateSerializer(serializers.ModelSerializer):
    floor = serializers.PrimaryKeyRelatedField(queryset=Floor.objects.all())
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Ward
        fields = [
            "floor",
            "department",
            "code",
            "name",
            "ward_type",
            "gender_restriction",
            "age_group",
        ]
        validators = []


class WardUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=255, required=False)
    ward_type = serializers.ChoiceField(Ward.WardType.choices, required=False)
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True
    )
    gender_restriction = serializers.ChoiceField(Ward.GenderRestriction.choices, required=False)
    age_group = serializers.ChoiceField(Ward.AgeGroup.choices, required=False)
    is_active = serializers.BooleanField(required=False)


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = [*COMMON_READ, "ward", "code", "name", "room_type", "is_isolation_capable"]
        read_only_fields = fields


class RoomCreateSerializer(serializers.ModelSerializer):
    ward = serializers.PrimaryKeyRelatedField(queryset=Ward.objects.all())

    class Meta:
        model = Room
        fields = ["ward", "code", "name", "room_type", "is_isolation_capable"]
        validators = []


class RoomUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=255, required=False)
    room_type = serializers.ChoiceField(Room.RoomType.choices, required=False)
    is_isolation_capable = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)
