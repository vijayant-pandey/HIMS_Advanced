"""The HIMS operations console: Django admin wired into HIMS RBAC and audit (ADR-016).

* Entry requires the ``platform.admin_console`` permission (or ``audit.view`` for auditors, who
  only see the audit log). There is no ``is_staff``/``is_superuser`` bypass.
* Sign-in failures are rate limited per client IP and audited.
* Two-factor (HIMS-IAM-005): accounts with an authenticator must enter its code on this form;
  privileged accounts without one are sent to the HIMS app's Security page to set it up first.
"""

from django import forms
from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction

MAX_FAILED_LOGINS = 5
LOCKOUT_SECONDS = 15 * 60


def can_use_console(user) -> bool:
    from apps.access_control.catalog import P
    from apps.access_control.selectors import has_permission

    return has_permission(user, P.ADMIN_CONSOLE)


def can_view_audit(user) -> bool:
    from apps.access_control.catalog import P
    from apps.access_control.selectors import has_permission

    return has_permission(user, P.AUDIT_VIEW)


class HimsAdminAuthenticationForm(AdminAuthenticationForm):
    otp_code = forms.CharField(
        label="Authenticator code",
        required=False,
        max_length=32,
        help_text="Only if two-factor sign-in is on for your account. A backup code also works.",
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}),
    )

    def _lockout_key(self) -> str:
        ip = self.request.META.get("REMOTE_ADDR", "unknown") if self.request else "unknown"
        return f"admin-login-failures:{ip}"

    def clean(self):
        key = self._lockout_key()
        if cache.get(key, 0) >= MAX_FAILED_LOGINS:
            raise ValidationError(
                "Too many failed sign-in attempts. Try again in 15 minutes.", code="locked"
            )
        try:
            cleaned = super().clean()
            self._check_second_factor()
        except ValidationError:
            cache.set(key, cache.get(key, 0) + 1, LOCKOUT_SECONDS)
            self._audit(outcome="failure")
            raise
        self._audit(outcome="success", actor=self.get_user())
        return cleaned

    def _check_second_factor(self) -> None:
        from apps.identity import mfa

        user = self.get_user()
        if mfa.confirmed_device(user) is not None:
            code = (self.cleaned_data.get("otp_code") or "").strip()
            if not code:
                raise ValidationError(
                    "Enter the code from your authenticator app.", code="mfa_code_missing"
                )
            try:
                with transaction.atomic():
                    mfa._check_code(user, code, allow_recovery=True)
            except mfa.InvalidMfaCode as exc:
                raise ValidationError(str(exc.detail), code="mfa_code_invalid") from exc
            self.request._hims_admin_mfa_verified = True
        elif mfa.is_required(user):
            raise ValidationError(
                "Your role requires two-factor sign-in. Set it up in the HIMS app "
                "(your name > Security) first, then sign in here.",
                code="mfa_setup_required",
            )
        else:
            self.request._hims_admin_mfa_verified = False

    def confirm_login_allowed(self, user):
        # Replaces Django's is_staff check with HIMS RBAC; same message as a wrong password
        # so the console does not reveal which accounts exist or what they can do.
        if not user.is_active or not (can_use_console(user) or can_view_audit(user)):
            raise ValidationError(
                self.error_messages["invalid_login"],
                code="invalid_login",
                params={"username": self.username_field.verbose_name},
            )

    def _audit(self, *, outcome: str, actor=None):
        from apps.audit.services import AuditAction, record_audit_event

        record_audit_event(
            action=AuditAction.AUTH_LOGIN
            if outcome == "success"
            else AuditAction.AUTH_LOGIN_FAILED,
            resource_type="admin_session",
            actor=actor,
            request=self.request,
            outcome=outcome,
            metadata={"via": "admin-console"},
        )


class HimsAdminSite(admin.AdminSite):
    site_header = "HIMS operations console"
    site_title = "HIMS console"
    index_title = "Administration (every change is audited)"
    login_form = HimsAdminAuthenticationForm

    def has_permission(self, request) -> bool:
        from apps.identity import mfa

        user = request.user
        return bool(
            user.is_active
            and user.is_authenticated
            and (can_use_console(user) or can_view_audit(user))
            and (mfa.session_verified(request) or not mfa.is_required(user))
        )

    def login(self, request, extra_context=None):
        response = super().login(request, extra_context)
        verified = getattr(request, "_hims_admin_mfa_verified", None)
        if verified is not None and request.user.is_authenticated:
            from apps.identity import mfa

            # Set after Django's login() so a session switch cannot drop the flag.
            mfa.mark_session_verified(request, verified)
        return response
