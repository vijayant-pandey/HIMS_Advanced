from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers

from common.validators import validate_timezone

from ..models import Department, Facility


def facility_counts(queryset):
    """Active departments per facility (shown before someone tries to deactivate it)."""
    return queryset.annotate(
        active_departments=Count(
            "departments", filter=Q(departments__status="active"), distinct=True
        )
    )


def department_counts(queryset):
    """Current staff postings and active wards per department."""
    today = timezone.localdate()
    current = Q(staff_assignments__valid_until__isnull=True) | Q(
        staff_assignments__valid_until__gte=today
    )
    return queryset.annotate(
        current_staff=Count("staff_assignments", filter=current, distinct=True),
        active_wards=Count("wards", filter=Q(wards__is_active=True), distinct=True),
    )


class FacilitySerializer(serializers.ModelSerializer):
    facility_type_label = serializers.CharField(source="get_facility_type_display", read_only=True)
    active_departments = serializers.SerializerMethodField()

    def get_active_departments(self, facility) -> int:
        cached = getattr(facility, "active_departments", None)
        if cached is not None:
            return cached
        return facility.departments.filter(status="active").count()

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
            "facility_type_label",
            "active_departments",
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
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    department_type_label = serializers.CharField(
        source="get_department_type_display", read_only=True
    )
    current_staff = serializers.SerializerMethodField(help_text="Staff posted here now or later.")
    active_wards = serializers.SerializerMethodField()

    def get_current_staff(self, department) -> int:
        cached = getattr(department, "current_staff", None)
        if cached is not None:
            return cached
        return department_counts(Department.objects.filter(pk=department.pk)).get().current_staff

    def get_active_wards(self, department) -> int:
        cached = getattr(department, "active_wards", None)
        if cached is not None:
            return cached
        return department.wards.filter(is_active=True).count()

    class Meta:
        model = Department
        fields = [
            "id",
            "facility",
            "facility_name",
            "code",
            "name",
            "department_type",
            "department_type_label",
            "status",
            "current_staff",
            "active_wards",
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
