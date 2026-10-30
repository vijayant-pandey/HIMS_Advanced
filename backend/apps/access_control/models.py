from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from common.models import OrganizationOwnedModel, UUIDPrimaryKeyModel, VersionedModel


class Permission(UUIDPrimaryKeyModel):
    """A permission codename, synchronised from ``catalog.PERMISSIONS``."""

    codename = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "permissions"
        ordering = ["codename"]

    def __str__(self) -> str:
        return self.codename


class Role(OrganizationOwnedModel, VersionedModel):
    code = models.SlugField(max_length=64)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False)
    permissions = models.ManyToManyField(Permission, through="RolePermission", related_name="roles")

    class Meta:
        db_table = "roles"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="roles_code_unique")
        ]

    def __str__(self) -> str:
        return self.name


class RolePermission(UUIDPrimaryKeyModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "role_permissions"
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="role_permission_unique")
        ]


class RoleAssignment(OrganizationOwnedModel):
    """Grants a role to a user, organization-wide or limited to a facility/department.

    Assignments are time-bounded and revoked rather than deleted, preserving access history
    for audit and periodic access reviews (spec 4.4, 13.2).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="role_assignments"
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="assignments")
    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    department = models.ForeignKey(
        "facilities.Department", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(blank=True)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    revocation_reason = models.TextField(blank=True)
    # Cover arrangements (HIMS-IAM-017): a copy of another person's assignment, lent for a
    # limited time. Both empty for ordinary access.
    delegation = models.ForeignKey(
        "AccessDelegation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    delegated_from = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="delegated_copies",
        help_text="The covered person's assignment this one copies.",
    )

    class Meta:
        db_table = "role_assignments"
        constraints = [
            models.CheckConstraint(
                condition=Q(department__isnull=True) | Q(facility__isnull=False),
                name="role_assignment_department_needs_facility",
            ),
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True) | Q(valid_until__gt=models.F("valid_from")),
                name="role_assignment_valid_range",
            ),
            models.UniqueConstraint(
                fields=["user", "role", "facility", "department"],
                condition=Q(revoked_at__isnull=True),
                nulls_distinct=False,
                name="role_assignment_active_unique",
            ),
        ]
        indexes = [models.Index(fields=["user", "revoked_at"], name="role_assignment_user_idx")]


class AccessReview(OrganizationOwnedModel, VersionedModel):
    """A periodic access review (HIMS-IAM-012; spec 4.4, 13.2 "periodic permission review").

    Starting a review takes a snapshot of everyone's current access (one item per role
    assignment). Reviewers confirm (keep) or remove each one; removing revokes the assignment
    through the normal service. A completed review is the evidence for auditors and is never
    deleted.
    """

    class Status(models.TextChoices):
        OPEN = "open", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    title = models.CharField(max_length=200)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    due_on = models.DateField()
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    notes = models.TextField(blank=True, help_text="Summary or reason for cancelling.")

    class Meta:
        db_table = "access_reviews"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization"],
                condition=Q(status="open"),
                name="access_review_one_open",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.get_status_display()})"


class AccessReviewItem(UUIDPrimaryKeyModel):
    """One person's role at one place, as it was when the review started, and the decision.

    The names are copied so the evidence still reads correctly after people or roles are renamed.
    """

    class Decision(models.TextChoices):
        PENDING = "pending", "Not reviewed yet"
        KEEP = "keep", "Keep"
        REMOVE = "remove", "Removed"
        ENDED = "ended", "Already ended elsewhere"

    review = models.ForeignKey(AccessReview, on_delete=models.PROTECT, related_name="items")
    assignment = models.ForeignKey(RoleAssignment, on_delete=models.PROTECT, related_name="+")
    person_name = models.CharField(max_length=255)
    person_email = models.EmailField()
    account_active = models.BooleanField(help_text="Could the person sign in when it started?")
    last_signed_in_at = models.DateTimeField(null=True, blank=True)
    role_name = models.CharField(max_length=128)
    scope = models.CharField(max_length=300, help_text='Where, e.g. "Whole hospital".')
    granted_at = models.DateTimeField()
    access_ends_at = models.DateTimeField(null=True, blank=True)
    decision = models.CharField(max_length=16, choices=Decision.choices, default=Decision.PENDING)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True)

    class Meta:
        db_table = "access_review_items"
        ordering = ["person_name", "role_name", "scope"]
        constraints = [
            models.UniqueConstraint(
                fields=["review", "assignment"], name="access_review_item_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.person_name}: {self.role_name} ({self.scope})"


class AccessReviewReminder(UUIDPrimaryKeyModel):
    """Each reminder email is sent once (HIMS-IAM-012): "a review is due" once per due date,
    "the review is overdue" once per open review."""

    class Kind(models.TextChoices):
        DUE = "due", "A review is due"
        OVERDUE = "overdue", "The review in progress is overdue"

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    due_on = models.DateField()
    review = models.ForeignKey(
        AccessReview, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    recipients = models.PositiveIntegerField(default=0)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "access_review_reminders"
        ordering = ["-sent_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "kind", "due_on"], name="access_review_reminder_once"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} ({self.due_on})"


class AccessDelegation(OrganizationOwnedModel, VersionedModel):
    """Cover arrangement (spec 4.4 "delegated access"; HIMS-IAM-017): for a limited time, one
    person (the delegate) works with some or all of another person's access (the delegator),
    e.g. during leave. The access is lent as copies of the delegator's role assignments
    (``RoleAssignment.delegation``), so every permission rule, scope and audit applies
    unchanged. Never deleted; ended early with a reason, or it simply runs out.
    """

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Starts later"
        ACTIVE = "active", "Active now"
        FINISHED = "finished", "Finished"
        ENDED_EARLY = "ended_early", "Ended early"

    delegator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The person being covered (whose access is lent).",
    )
    delegate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The person covering.",
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reason = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    ended_at = models.DateTimeField(null=True, blank=True)
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    end_reason = models.TextField(blank=True)

    class Meta:
        db_table = "access_delegations"
        ordering = ["-starts_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")),
                name="access_delegation_valid_period",
            ),
            models.CheckConstraint(
                condition=~Q(delegator=models.F("delegate")),
                name="access_delegation_two_people",
            ),
        ]
        indexes = [
            models.Index(fields=["delegate", "ends_at"], name="access_deleg_delegate_idx"),
            models.Index(fields=["delegator", "ends_at"], name="access_deleg_delegator_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.delegate} covers {self.delegator}"

    @property
    def status(self) -> str:
        now = timezone.now()
        if self.ended_at is not None:
            return self.Status.ENDED_EARLY
        if now < self.starts_at:
            return self.Status.SCHEDULED
        if now >= self.ends_at:
            return self.Status.FINISHED
        return self.Status.ACTIVE
