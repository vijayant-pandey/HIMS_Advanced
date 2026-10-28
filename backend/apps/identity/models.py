from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from common.models import UUIDPrimaryKeyModel


class UserManager(BaseUserManager):
    use_in_migrations = True

    def get_by_natural_key(self, username):
        return self.get(email__iexact=username)

    def create_user(self, email: str, display_name: str, password: str | None = None, **extra):
        user = self.model(email=email.strip().lower(), display_name=display_name, **extra)
        if password:
            user.set_password(password)
            user.password_changed_at = timezone.now()
        else:
            user.set_unusable_password()
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user


class User(UUIDPrimaryKeyModel, AbstractBaseUser):
    """A login identity within this deployment.

    Authorization comes only from role assignments (apps.access_control); there is no
    superuser flag that bypasses them. Professional identity lives in apps.staff.
    """

    email = models.EmailField(max_length=254, unique=True)  # stored lower-cased
    display_name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)
    password_changed_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["display_name"]

    class Meta:
        db_table = "users"
        constraints = [models.UniqueConstraint(Lower("email"), name="users_email_ci_unique")]

    def clean(self):
        super().clean()
        self.email = self.email.strip().lower()
        switching_off = (
            not self._state.adding
            and not self.is_active
            and User.objects.filter(pk=self.pk, is_active=True).exists()
        )
        if switching_off:
            from django.core.exceptions import ValidationError

            from common.exceptions import ConflictError

            from .accounts import ensure_not_last_administrator

            try:
                ensure_not_last_administrator(self)
            except ConflictError as exc:
                raise ValidationError({"is_active": exc.detail}) from exc

    def __str__(self) -> str:
        return self.display_name


class Invitation(UUIDPrimaryKeyModel):
    """An invitation for a user to activate their account by choosing a password (spec 4.4).

    The emailed link carries a signed reference to this row (see invitations.make_token); the
    secret itself is never stored. Single use, time-limited, and revoked when a newer
    invitation is issued for the same user.
    """

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="invitations")
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_invitations"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(accepted_at__isnull=True, revoked_at__isnull=True),
                name="user_invitation_one_open",
            )
        ]

    def __str__(self) -> str:
        return f"Invitation for {self.user_id} ({self.status})"

    @property
    def status(self) -> str:
        if self.accepted_at:
            return "accepted"
        if self.revoked_at:
            return "revoked"
        if self.expires_at <= timezone.now():
            return "expired"
        return "open"


class PasswordReset(UUIDPrimaryKeyModel):
    """A "forgot password" request (spec 13.1: secure account recovery).

    Like invitations, the emailed link carries a signed reference to this row; the secret is
    never stored. Short-lived, single use, and superseded by any newer request for the user.
    """

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="password_resets")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_password_resets"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(used_at__isnull=True, revoked_at__isnull=True),
                name="user_password_reset_one_open",
            )
        ]
        indexes = [models.Index(fields=["user", "created_at"], name="password_reset_user_idx")]

    def __str__(self) -> str:
        return f"Password reset for {self.user_id} ({self.status})"

    @property
    def status(self) -> str:
        if self.used_at:
            return "used"
        if self.revoked_at:
            return "revoked"
        if self.expires_at <= timezone.now():
            return "expired"
        return "open"


class UserSession(UUIDPrimaryKeyModel):
    """Register of sign-in sessions per user (HIMS-IAM-006; spec 4.4, 13.2, 13.5).

    Django's session table cannot be searched by user, so this register records which session
    belongs to whom. It lets HIMS end every session of a person at once (suspension, termination,
    password change, "sign out of all devices") and shows administrators how many devices were
    signed out. The session key is a bearer secret: it is never shown in the admin or the API.
    """

    class EndReason(models.TextChoices):
        LOGOUT = "logout", "Signed out"
        ACCOUNT_DEACTIVATED = "account_deactivated", "Account deactivated (suspended/terminated)"
        PASSWORD_CHANGED = "password_changed", "Password changed"
        SIGNED_OUT_BY_ADMIN = "signed_out_by_admin", "Signed out by an administrator"
        EXPIRED = "expired", "Expired"

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="sessions")
    session_key = models.CharField(max_length=40, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    end_reason = models.CharField(max_length=32, choices=EndReason.choices, blank=True)

    class Meta:
        db_table = "user_sessions"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "ended_at"], name="user_session_open_idx")]

    def __str__(self) -> str:
        state = self.get_end_reason_display() if self.ended_at else "active"
        return f"Session of {self.user_id} ({state})"


class MfaDevice(UUIDPrimaryKeyModel):
    """A user's authenticator app for two-factor sign-in (HIMS-IAM-005; spec 4.4, 13.1).

    The TOTP secret is stored encrypted (common.crypto, spec 13.3) because it must be read to
    check codes. ``confirmed_at`` is empty while setup is in progress; only confirmed devices are
    used at sign-in. ``last_used_step`` blocks re-use of a code that was already accepted.
    """

    user = models.OneToOneField(User, on_delete=models.PROTECT, related_name="mfa_device")
    secret_encrypted = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    last_used_step = models.BigIntegerField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_mfa_devices"

    def __str__(self) -> str:
        return f"Authenticator for {self.user_id} ({'on' if self.confirmed_at else 'setting up'})"


class MfaRecoveryCode(UUIDPrimaryKeyModel):
    """One-time backup code for a lost phone. Only a SHA-256 fingerprint is stored."""

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="mfa_recovery_codes")
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_mfa_recovery_codes"
        constraints = [
            models.UniqueConstraint(fields=["user", "code_hash"], name="mfa_recovery_code_unique")
        ]

    def __str__(self) -> str:
        return f"Recovery code for {self.user_id} ({'used' if self.used_at else 'unused'})"
