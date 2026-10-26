from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm
from django.contrib.auth.forms import UserChangeForm as DjangoUserChangeForm
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError

from apps.access_control.models import RoleAssignment
from apps.audit.services import record_audit_event
from common.admin.options import HimsInline, HimsModelAdmin, ReadOnlyModelAdmin
from common.exceptions import DomainError

from .invitations import issue_invitation
from .models import Invitation, PasswordReset, User, UserSession
from .sessions import end_user_sessions, track_session


def send_invitations(model_admin, request, users) -> None:
    """Shared admin action body: (re)send activation emails, reporting per-user problems."""
    sent = 0
    for user in users:
        try:
            issue_invitation(user=user, actor=request.user, request=request)
            sent += 1
        except DomainError as exc:
            model_admin.message_user(request, f"{user.email}: {exc.detail}", messages.WARNING)
    if sent:
        model_admin.message_user(request, f"Sent {sent} invitation email(s).")


@admin.register(PasswordReset)
class PasswordResetAdmin(ReadOnlyModelAdmin):
    """Status only. Links cannot be recovered here: tokens are never stored."""

    list_display = ("user", "status", "created_at", "expires_at", "used_at")
    search_fields = ("user__email",)
    readonly_fields = ("status",)


@admin.register(UserSession)
class UserSessionAdmin(ReadOnlyModelAdmin):
    """Who is signed in where. The session key is a secret and is never displayed."""

    list_display = ("user", "created_at", "ip_address", "ended_at", "end_reason")
    list_filter = (("ended_at", admin.EmptyFieldListFilter), "end_reason")
    search_fields = ("user__email", "user__display_name", "ip_address")
    exclude = ("session_key",)


@admin.register(Invitation)
class InvitationAdmin(ReadOnlyModelAdmin):
    """Status only. Links cannot be recovered here: tokens are never stored."""

    list_display = ("user", "status", "created_at", "expires_at", "accepted_at", "created_by")
    list_filter = (
        ("accepted_at", admin.EmptyFieldListFilter),
        ("revoked_at", admin.EmptyFieldListFilter),
    )
    search_fields = ("user__email", "user__display_name")
    readonly_fields = ("status",)


# HIMS authorization lives in apps.access_control (roles + scoped assignments); Django's
# groups/permissions tables are unused, so their admin page would only mislead.
if admin.site.is_registered(Group):
    admin.site.unregister(Group)


class UserCreationForm(AdminUserCreationForm):
    class Meta:
        model = User
        fields = ("email", "display_name")
        field_classes = {}

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email


class UserChangeForm(DjangoUserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


class RoleAssignmentInline(HimsInline):
    """Read-only view of a user's grants. Grant and revoke under Role assignments."""

    model = RoleAssignment
    fk_name = "user"
    fields = ("role", "facility", "department", "valid_from", "valid_until", "revoked_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(HimsModelAdmin, DjangoUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    list_display = ("email", "display_name", "is_active", "last_login", "date_joined")
    list_filter = ("is_active",)
    search_fields = ("email", "display_name")
    ordering = ("email",)
    filter_horizontal = ()
    readonly_fields = ("last_login", "date_joined", "password_changed_at")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("display_name",)}),
        ("Status", {"fields": ("is_active", "last_login", "date_joined", "password_changed_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "display_name", "usable_password", "password1", "password2"),
            },
        ),
    )
    inlines = [RoleAssignmentInline]
    actions = ["send_invitation", "sign_out_everywhere"]

    @admin.action(description="Send invitation email (activate account)")
    def send_invitation(self, request, queryset):
        send_invitations(self, request, queryset)

    @admin.action(description="Sign out of all devices")
    def sign_out_everywhere(self, request, queryset):
        total = 0
        for user in queryset:
            total += end_user_sessions(
                user,
                reason=UserSession.EndReason.SIGNED_OUT_BY_ADMIN,
                actor=request.user,
                request=request,
                # Never sign the administrator out of the console they are using.
                keep_session_key=request.session.session_key,
            )
        self.message_user(request, f"Signed out {total} session(s).")

    def user_change_password(self, request, id, form_url=""):
        response = super().user_change_password(request, id, form_url)
        if request.method == "POST" and response.status_code == 302:
            record_audit_event(
                action="admin.user.password_set",
                resource_type="user",
                resource_id=id,
                request=request,
                metadata={"via": "admin-console"},
            )
            user = User.objects.get(pk=id)
            changing_own = user.pk == request.user.pk
            # A new password signs the person out everywhere (except this console tab when an
            # administrator changes their own password; Django already rotated its key).
            end_user_sessions(
                user,
                reason=UserSession.EndReason.PASSWORD_CHANGED,
                actor=request.user,
                request=request,
                keep_session_key=request.session.session_key if changing_own else None,
            )
            if changing_own:
                track_session(request, user)
        return response
