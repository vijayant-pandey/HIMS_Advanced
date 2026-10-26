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
