from django.contrib import admin

from common.admin.options import HimsInline, HimsModelAdmin

from .models import Building, Department, Facility, Floor, Room, Ward


class DepartmentInline(HimsInline):
    model = Department
    fields = ("code", "name", "department_type", "status")


class BuildingInline(HimsInline):
    model = Building
    fields = ("code", "name", "is_active")


@admin.register(Facility)
class FacilityAdmin(HimsModelAdmin):
    list_display = ("code", "name", "facility_type", "city", "timezone", "status")
    list_filter = ("status", "facility_type", "country")
    search_fields = ("code", "name", "city")
    fieldsets = (
        (None, {"fields": ("organization", "code", "name", "facility_type", "status")}),
        (
            "Location",
            {
                "fields": (
                    "country",
                    "state_region",
                    "city",
                    "address_line1",
                    "address_line2",
                    "postal_code",
                    "timezone",
                    "phone",
                )
            },
        ),
        ("Record", {"fields": ("version", "created_at", "updated_at")}),
    )
    inlines = [DepartmentInline, BuildingInline]


@admin.register(Department)
class DepartmentAdmin(HimsModelAdmin):
    list_display = ("code", "name", "facility", "department_type", "status")
    list_filter = ("status", "department_type", "facility")
    search_fields = ("code", "name")
    fields = (
        "organization",
        "facility",
        "code",
        "name",
        "department_type",
        "status",
        "version",
        "created_at",
        "updated_at",
    )


# --- Locations (HIMS-FAC-004). Organization/facility are derived from the parent; parents ------
# cannot change after creation, so the parent field is read-only when editing.


class _LocationAdmin(HimsModelAdmin):
    parent_field = ""

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            readonly += [self.parent_field, "code"] if hasattr(obj, "code") else [self.parent_field]
        return readonly


class FloorInline(HimsInline):
    model = Floor
    fields = ("level", "name", "is_active")


class WardInline(HimsInline):
    model = Ward
    fk_name = "floor"
    fields = ("code", "name", "ward_type", "department", "is_active")


class RoomInline(HimsInline):
    model = Room
    fields = ("code", "name", "room_type", "is_isolation_capable", "is_active")


@admin.register(Building)
class BuildingAdmin(_LocationAdmin):
    parent_field = "facility"
    inlines = [FloorInline]
    list_display = ("code", "name", "facility", "is_active")
    list_filter = ("is_active", "facility")
    search_fields = ("code", "name")
    fields = ("facility", "code", "name", "is_active", "version", "created_at", "updated_at")


@admin.register(Floor)
class FloorAdmin(_LocationAdmin):
    parent_field = "building"
    inlines = [WardInline]
    list_display = ("name", "level", "building", "is_active")
    list_filter = ("is_active", "building__facility")
    search_fields = ("name", "building__name")
    fields = ("building", "level", "name", "is_active", "version", "created_at", "updated_at")


@admin.register(Ward)
class WardAdmin(_LocationAdmin):
    parent_field = "floor"
    inlines = [RoomInline]
    list_display = ("code", "name", "ward_type", "floor", "department", "is_active")
    list_filter = ("is_active", "ward_type", "facility")
    search_fields = ("code", "name")
    fields = (
        "floor",
        "code",
        "name",
        "ward_type",
        "department",
        "gender_restriction",
        "age_group",
        "is_active",
        "version",
        "created_at",
        "updated_at",
    )


@admin.register(Room)
class RoomAdmin(_LocationAdmin):
    parent_field = "ward"
    list_display = ("code", "name", "room_type", "ward", "is_isolation_capable", "is_active")
    list_filter = ("is_active", "room_type", "facility")
    search_fields = ("code", "name", "ward__name")
    fields = (
        "ward",
        "code",
        "name",
        "room_type",
        "is_isolation_capable",
        "is_active",
        "version",
        "created_at",
        "updated_at",
    )
