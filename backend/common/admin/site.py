"""The HIMS operations console: Django admin wired into HIMS RBAC and audit (ADR-016).

* Entry requires the ``platform.admin_console`` permission (or ``audit.view`` for auditors, who
  only see the audit log). There is no ``is_staff``/``is_superuser`` bypass.
* Sign-in failures are rate limited per client IP and audited.
"""

from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.cache import cache
from django.core.exceptions import ValidationError

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
            return super().clean()
        except ValidationError:
            cache.set(key, cache.get(key, 0) + 1, LOCKOUT_SECONDS)
            self._audit(outcome="failure")
            raise

    def confirm_login_allowed(self, user):
        # Replaces Django's is_staff check with HIMS RBAC; same message as a wrong password
        # so the console does not reveal which accounts exist or what they can do.
        if not user.is_active or not (can_use_console(user) or can_view_audit(user)):
            raise ValidationError(
                self.error_messages["invalid_login"],
                code="invalid_login",
                params={"username": self.username_field.verbose_name},
            )
        self._audit(outcome="success", actor=user)

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
        user = request.user
        return bool(
            user.is_active
            and user.is_authenticated
            and (can_use_console(user) or can_view_audit(user))
        )
