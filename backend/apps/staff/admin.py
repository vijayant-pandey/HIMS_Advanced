from django.contrib import admin, messages

from common.admin.options import HimsInline, HimsModelAdmin
from common.exceptions import DomainError

from .models import (
    QualificationType,
    Specialty,
    StaffCredential,
    StaffDepartmentAssignment,
    StaffMember,
    StaffQualification,
)
from .services import apply_employment_status_change, emit_staff_created, verify_credential

VERIFICATION_FIELDS = ("verification_status", "verified_by", "verified_at")


class StaffDepartmentAssignmentInline(HimsInline):
    model = StaffDepartmentAssignment
    fields = ("department", "designation", "specialty", "is_primary", "valid_from", "valid_until")


class StaffQualificationInline(HimsInline):
    model = StaffQualification
    fields = (
        "qualification_type",
        "specialty",
        "institution",
        "year_awarded",
        *VERIFICATION_FIELDS,
    )
    readonly_fields = VERIFICATION_FIELDS


class StaffCredentialInline(HimsInline):
    model = StaffCredential
    fields = (
        "credential_type",
        "registration_number",
        "issuing_authority",
        "jurisdiction",
        "valid_from",
        "expires_at",
        *VERIFICATION_FIELDS,
    )
    readonly_fields = VERIFICATION_FIELDS


@admin.register(StaffMember)
class StaffMemberAdmin(HimsModelAdmin):
    list_display = (
        "employee_number",
        "given_name",
        "family_name",
        "staff_type",
        "employment_status",
        "user",
    )
    list_filter = ("staff_type", "employment_status")
    search_fields = ("employee_number", "given_name", "family_name", "user__email")
    autocomplete_fields = ("user",)
    fields = (
        "organization",
        "user",
        "employee_number",
        "given_name",
        "family_name",
        "staff_type",
        "employment_status",
        "joined_on",
        "left_on",
        "version",
        "created_at",
        "updated_at",
    )
    inlines = [StaffDepartmentAssignmentInline, StaffQualificationInline, StaffCredentialInline]

    def save_model(self, request, obj, form, change):
        status_changed = change and "employment_status" in form.changed_data
        super().save_model(request, obj, form, change)
        # Same side effects as the API (login disabled on termination, outbox events).
        if not change:
            emit_staff_created(obj)
        elif status_changed:
            apply_employment_status_change(obj)


@admin.register(StaffCredential)
class StaffCredentialAdmin(HimsModelAdmin):
    list_display = (
        "staff",
        "credential_type",
        "registration_number",
        "issuing_authority",
        "expires_at",
        "verification_status",
    )
    list_filter = ("credential_type", "verification_status")
    search_fields = ("registration_number", "staff__family_name", "staff__employee_number")
    readonly_fields = VERIFICATION_FIELDS
    actions = ["mark_verified", "mark_rejected"]

    def _verify(self, request, queryset, verified: bool):
        done = 0
        for credential in queryset:
            try:
                verify_credential(
                    actor=request.user,
                    credential_id=credential.pk,
                    verified=verified,
                    request=request,
                    reason="Verified via admin console",
                )
                done += 1
            except DomainError as exc:
                self.message_user(
                    request, f"{credential.registration_number}: {exc.detail}", messages.ERROR
                )
        self.message_user(request, f"Updated {done} credential(s).")

    @admin.action(description="Mark selected credentials as verified")
    def mark_verified(self, request, queryset):
        self._verify(request, queryset, verified=True)

    @admin.action(description="Mark selected credentials as rejected")
    def mark_rejected(self, request, queryset):
        self._verify(request, queryset, verified=False)


@admin.register(Specialty)
class SpecialtyAdmin(HimsModelAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(QualificationType)
class QualificationTypeAdmin(HimsModelAdmin):
    list_display = ("code", "name", "category", "country", "is_active")
    list_filter = ("category", "country", "is_active")
    search_fields = ("code", "name")
