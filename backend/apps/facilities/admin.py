from django.contrib import admin

from common.admin.options import HimsInline, HimsModelAdmin

from .models import Department, Facility


class DepartmentInline(HimsInline):
    model = Department
    fields = ("code", "name", "department_type", "status")


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
    inlines = [DepartmentInline]


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
