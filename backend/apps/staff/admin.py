from django import forms
from django.contrib import admin, messages

from apps.identity.admin import send_invitations
from common.admin.options import HimsInline, HimsModelAdmin, ReadOnlyModelAdmin
from common.exceptions import DomainError

from .models import (
    CredentialExpiryAlert,
    Designation,
    QualificationType,
    Specialty,
    StaffCredential,
    StaffDepartmentAssignment,
    StaffDocument,
    StaffMember,
    StaffQualification,
)
from .services import apply_employment_status_change, emit_staff_created, verify_credential

VERIFICATION_FIELDS = ("verification_status", "verified_by", "verified_at")


class StaffMemberForm(forms.ModelForm):
    """Stops the console from suspending or terminating the hospital's last administrator."""

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("employment_status")
        user = self.instance.user if self.instance.pk else None
        losing_access = status in (
            StaffMember.EmploymentStatus.SUSPENDED,
            StaffMember.EmploymentStatus.TERMINATED,
        )
        if user is not None and user.is_active and losing_access:
            from apps.identity.accounts import ensure_not_last_administrator
            from common.exceptions import ConflictError

            try:
                ensure_not_last_administrator(user)
            except ConflictError as exc:
                self.add_error("employment_status", exc.detail)
        return cleaned


class StaffDepartmentAssignmentInline(HimsInline):
    model = StaffDepartmentAssignment
    fields = ("department", "designation", "specialty", "is_primary", "valid_from", "valid_until")
    autocomplete_fields = ("designation",)


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
    actions = ["send_invitation"]

    @admin.action(description="Send invitation email to selected staff")
    def send_invitation(self, request, queryset):
        without_login = queryset.filter(user__isnull=True).count()
        if without_login:
            self.message_user(
                request, f"{without_login} selected staff have no login account.", messages.WARNING
            )
        users = [staff.user for staff in queryset.select_related("user") if staff.user_id]
        send_invitations(self, request, users)

    form = StaffMemberForm

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


class _CatalogAdmin(HimsModelAdmin):
    """Job titles, specialties, qualification types (HIMS-STAFF-010): codes never change once
    created (records point to them); entries added here are marked as the hospital's own."""

    def get_readonly_fields(self, request, obj=None):
        readonly = [*super().get_readonly_fields(request, obj), "is_custom"]
        if obj is not None:
            readonly.append("code")
        return readonly

    def save_model(self, request, obj, form, change):
        if not change:
            obj.is_custom = True
        super().save_model(request, obj, form, change)


@admin.register(Designation)
class DesignationAdmin(_CatalogAdmin):
    list_display = ("name", "category", "country", "seniority", "is_custom", "is_active")
    list_filter = ("category", "country", "is_active")
    search_fields = ("code", "name")
    ordering = ("category", "seniority", "name")


@admin.register(Specialty)
class SpecialtyAdmin(_CatalogAdmin):
    list_display = ("code", "name", "is_custom", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(QualificationType)
class QualificationTypeAdmin(_CatalogAdmin):
    list_display = ("code", "name", "category", "country", "is_custom", "is_active")
    list_filter = ("category", "country", "is_active")
    search_fields = ("code", "name")


# --- Documents and expiry alerts (HIMS-STAFF-005/006) ----------------------------------------


class StaffDocumentForm(forms.ModelForm):
    """Same file checks as the app; a file is never replaced (archive and upload a new one)."""

    archive_reason_input = forms.CharField(
        required=False,
        max_length=255,
        label="Archive with reason",
        help_text="Fill in to archive this document (e.g. 'Wrong file'). It is never deleted.",
    )

    class Meta:
        model = StaffDocument
        fields = ("staff", "credential", "qualification", "file")

    def clean_file(self):
        upload = self.cleaned_data.get("file")
        if upload is not None and hasattr(upload, "content_type"):  # a newly uploaded file
            from .uploads import validate_upload

            self.detected = validate_upload(upload)  # plain-language error shown on the field
        return upload


@admin.register(StaffDocument)
class StaffDocumentAdmin(HimsModelAdmin):
    form = StaffDocumentForm
    list_display = (
        "original_name",
        "staff",
        "attached_to",
        "size",
        "uploaded_by",
        "created_at",
        "archived",
    )
    list_filter = ("content_type",)
    search_fields = ("original_name", "staff__family_name", "staff__employee_number")
    readonly_fields = (
        "open_file",
        "original_name",
        "content_type",
        "size_bytes",
        "sha256",
        "uploaded_by",
        "archived_at",
        "archived_by",
        "archive_reason",
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            readonly += ["staff", "credential", "qualification", "file"]
        return readonly

    def get_fields(self, request, obj=None):
        fields = ["staff", "credential", "qualification", "file", "open_file"]
        if obj is not None:
            fields += [
                "original_name",
                "content_type",
                "size_bytes",
                "sha256",
                "uploaded_by",
                "archived_at",
                "archived_by",
                "archive_reason",
            ]
            if obj.archived_at is None:
                fields.append("archive_reason_input")
        return fields

    @admin.display(description="Attached to")
    def attached_to(self, obj):
        return obj.credential or obj.qualification

    @admin.display(description="Size")
    def size(self, obj):
        return f"{obj.size_bytes / 1024:.0f} KB"

    @admin.display(boolean=True, description="Archived")
    def archived(self, obj):
        return obj.archived_at is not None

    @admin.display(description="File")
    def open_file(self, obj):
        from django.utils.html import format_html

        if not obj or not obj.pk:
            return "Shown after saving"
        url = f"/api/v1/staff-documents/{obj.pk}/download/?inline=true"
        return format_html('<a href="{}" target="_blank" rel="noopener">Open (audited)</a>', url)

    def save_model(self, request, obj, form, change):
        from .documents import archive_document
        from .uploads import safe_original_name, sha256_of

        if not change:
            upload = form.cleaned_data["file"]
            obj.organization_id = obj.staff.organization_id
            obj.original_name = safe_original_name(upload.name)
            obj.content_type = form.detected[0]
            obj.size_bytes = upload.size
            obj.sha256 = sha256_of(upload)
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)
        reason = form.cleaned_data.get("archive_reason_input")
        if change and reason and obj.archived_at is None:
            archive_document(actor=request.user, document_id=obj.pk, reason=reason, request=request)


@admin.register(CredentialExpiryAlert)
class CredentialExpiryAlertAdmin(ReadOnlyModelAdmin):
    list_display = ("credential", "stage", "expires_at", "recipients", "sent_at")
    list_filter = ("days_before",)
    date_hierarchy = "sent_at"

    @admin.display(description="Stage")
    def stage(self, obj):
        return "Expired" if obj.days_before == 0 else f"{obj.days_before} days before"
