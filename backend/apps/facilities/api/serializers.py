from rest_framework import serializers

from common.validators import validate_timezone

from ..models import Department, Facility


class FacilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Facility
        fields = [
            "id",
            "code",
            "name",
            "facility_type",
            "country",
            "state_region",
            "city",
            "address_line1",
            "address_line2",
            "postal_code",
            "timezone",
            "phone",
            "status",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class FacilityCreateSerializer(serializers.ModelSerializer):
    timezone = serializers.CharField(max_length=64, validators=[validate_timezone])

    class Meta:
        model = Facility
        fields = [
            "code",
            "name",
            "facility_type",
            "country",
            "state_region",
            "city",
            "address_line1",
            "address_line2",
            "postal_code",
            "timezone",
            "phone",
        ]
        # Uniqueness is enforced by the service and database (409, not 400).
        validators = []


class FacilityUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=255, required=False)
    facility_type = serializers.ChoiceField(Facility.FacilityType.choices, required=False)
    state_region = serializers.CharField(max_length=100, required=False)
    city = serializers.CharField(max_length=100, required=False)
    address_line1 = serializers.CharField(max_length=255, required=False)
    address_line2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=20, required=False)
    timezone = serializers.CharField(max_length=64, required=False, validators=[validate_timezone])
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    status = serializers.ChoiceField(Facility.Status.choices, required=False)


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = [
            "id",
            "facility",
            "code",
            "name",
            "department_type",
            "status",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class DepartmentCreateSerializer(serializers.ModelSerializer):
    facility = serializers.PrimaryKeyRelatedField(queryset=Facility.objects.all())

    class Meta:
        model = Department
        fields = ["facility", "code", "name", "department_type"]
        validators = []


class DepartmentUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=255, required=False)
    department_type = serializers.ChoiceField(Department.DepartmentType.choices, required=False)
    status = serializers.ChoiceField(Department.Status.choices, required=False)
