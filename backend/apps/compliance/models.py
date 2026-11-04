from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from common.models import TimeStampedModel, UUIDPrimaryKeyModel, VersionedModel


class ComplianceRequirement(UUIDPrimaryKeyModel, TimeStampedModel, VersionedModel):
    """One legal or regulatory obligation and how far the hospital has met it (spec 13, 26.7;
    HIMS-COMP-001/002/003). Wording comes from catalog.py; status and evidence are the hospital's.
    Implemented in software does not mean compliant: "verified" needs written evidence."""

    class Jurisdiction(models.TextChoices):
        ALL = "ALL", "Both countries"
        IN = "IN", "India"
        US = "US", "United States"

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        IN_PROGRESS = "in_progress", "In progress"
        IMPLEMENTED = "implemented", "Implemented, not verified"
        VERIFIED = "verified", "Verified with evidence"
        NOT_APPLICABLE = "not_applicable", "Not applicable"

    code = models.CharField(max_length=40, unique=True)
    jurisdiction = models.CharField(max_length=3, choices=Jurisdiction.choices)
    regulation = models.CharField(max_length=120)
    citation = models.CharField(max_length=120, blank=True)
    title = models.CharField(max_length=200)
    summary = models.TextField(help_text="What the law asks, in plain words.")
    hims_support = models.TextField(blank=True, help_text="What HIMS does for it today.")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NOT_STARTED)
    owner = models.CharField(max_length=150, blank=True, help_text="Who answers for it.")
    evidence = models.TextField(blank=True, help_text="Where the proof is; required to verify.")
    next_review_on = models.DateField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "compliance_requirements"
        ordering = ["jurisdiction", "code"]
        indexes = [
            models.Index(fields=["jurisdiction", "status"], name="compliance_req_status_idx")
        ]

    def __str__(self) -> str:
        return f"{self.code}: {self.title}"


class RiskEntry(UUIDPrimaryKeyModel, TimeStampedModel, VersionedModel):
    """One line of the risk register (spec 23 "threat model and risk assessment"; HIPAA
    164.308(a)(1); HIMS-COMP-005). Score = likelihood x impact, each 1 to 5."""

    class Treatment(models.TextChoices):
        MITIGATE = "mitigate", "Reduce it"
        ACCEPT = "accept", "Accept it"
        TRANSFER = "transfer", "Transfer it (e.g. insurance, vendor)"
        AVOID = "avoid", "Avoid it"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        TREATING = "treating", "Being treated"
        ACCEPTED = "accepted", "Accepted"
        CLOSED = "closed", "Closed"

    code = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=40, help_text="e.g. access, data, availability.")
    likelihood = models.PositiveSmallIntegerField(default=3)
    impact = models.PositiveSmallIntegerField(default=3)
    treatment = models.CharField(
        max_length=10, choices=Treatment.choices, default=Treatment.MITIGATE
    )
    mitigation = models.TextField(blank=True, help_text="What reduces it, done and planned.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    owner = models.CharField(max_length=150, blank=True)
    review_on = models.DateField(null=True, blank=True)
    acceptance_reason = models.TextField(blank=True, help_text="Required to accept a risk.")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "compliance_risks"
        ordering = ["code"]
        constraints = [
            models.CheckConstraint(
                condition=Q(likelihood__gte=1, likelihood__lte=5, impact__gte=1, impact__lte=5),
                name="compliance_risk_scale_1_to_5",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code}: {self.title}"

    @property
    def score(self) -> int:
        return self.likelihood * self.impact


class SecurityIncident(UUIDPrimaryKeyModel, TimeStampedModel, VersionedModel):
    """A security incident or suspected breach (HIPAA 164.308(a)(6); DPDP Rule 7; CERT-In
    directions; spec 13.4; HIMS-COMP-004). Never deleted. Must not hold clinical details."""

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        REPORTED = "reported", "Reported"
        INVESTIGATING = "investigating", "Investigating"
        CONTAINED = "contained", "Contained"
        CLOSED = "closed", "Closed"

    title = models.CharField(max_length=200)
    description = models.TextField(help_text="What happened. No patient details.")
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.MEDIUM)
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.REPORTED)
    detected_at = models.DateTimeField(
        default=timezone.now, help_text="When it was noticed: legal deadlines count from here."
    )
    occurred_at = models.DateTimeField(null=True, blank=True)
    personal_data_affected = models.BooleanField(default=False)
    people_affected = models.PositiveIntegerField(null=True, blank=True)
    actions_taken = models.TextField(blank=True)
    closure_summary = models.TextField(blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "security_incidents"
        ordering = ["-detected_at"]
        indexes = [
            models.Index(fields=["status", "detected_at"], name="security_incident_open_idx")
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(occurred_at__isnull=True) | Q(occurred_at__lte=F("detected_at")),
                name="security_incident_occurred_first",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.get_status_display()})"


class BrowserSecurityReport(UUIDPrimaryKeyModel, TimeStampedModel, VersionedModel):
    """Something a browser blocked under the security headers, added up per day (spec 13;
    HIMS-SEC-012). Browsers send these without signing in, so the content is not trustworthy
    and holds no query strings or code samples."""

    day = models.DateField()
    directive = models.CharField(max_length=64, help_text="The rule that blocked it.")
    blocked = models.CharField(max_length=200, help_text="The site or kind of code blocked.")
    page_path = models.CharField(max_length=200, blank=True, help_text="Page, ids removed.")
    occurrences = models.PositiveIntegerField(default=1)
    last_seen_at = models.DateTimeField(default=timezone.now)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        db_table = "browser_security_reports"
        ordering = ["-day", "-occurrences"]
        constraints = [
            models.UniqueConstraint(
                fields=["day", "directive", "blocked", "page_path"],
                name="browser_report_unique_per_day",
            )
        ]

    def __str__(self) -> str:
        return f"{self.day}: {self.directive} blocked {self.blocked}"


class IncidentNotification(UUIDPrimaryKeyModel, TimeStampedModel):
    """One notification the law requires for an incident, with its deadline (see incidents.py)."""

    class Kind(models.TextChoices):
        CERT_IN = "cert_in", "India: CERT-In report"
        DPDP_BOARD_INITIAL = "dpdp_board_initial", "India: Data Protection Board, first notice"
        DPDP_BOARD_DETAILED = "dpdp_board_detailed", "India: Data Protection Board, detailed report"
        DPDP_PEOPLE = "dpdp_people", "India: tell the affected people"
        HIPAA_INDIVIDUALS = "hipaa_individuals", "US: tell the affected people"
        HIPAA_HHS = "hipaa_hhs", "US: tell HHS"
        HIPAA_MEDIA = "hipaa_media", "US: tell the media (over 500 people)"

    class Status(models.TextChoices):
        PENDING = "pending", "To do"
        DONE = "done", "Done"
        NOT_REQUIRED = "not_required", "Not required"

    incident = models.ForeignKey(
        SecurityIncident, on_delete=models.PROTECT, related_name="notifications"
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    due_at = models.DateTimeField()
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.PENDING)
    done_at = models.DateTimeField(null=True, blank=True)
    done_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    reference = models.CharField(max_length=200, blank=True, help_text="e.g. acknowledgement no.")
    note = models.TextField(blank=True, help_text="Required when marked not required.")
    soon_alert_sent_at = models.DateTimeField(null=True, blank=True)
    overdue_alert_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "security_incident_notifications"
        ordering = ["due_at"]
        constraints = [
            models.UniqueConstraint(fields=["incident", "kind"], name="incident_notification_once"),
        ]
        indexes = [models.Index(fields=["status", "due_at"], name="incident_notif_due_idx")]

    def __str__(self) -> str:
        return self.get_kind_display()
