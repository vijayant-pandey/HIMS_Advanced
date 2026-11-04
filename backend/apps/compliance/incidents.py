"""Security incidents and their legal deadlines (HIPAA 164.308(a)(6), 164.404/406/408; DPDP
Rule 7; CERT-In directions; spec 13.4; HIMS-COMP-004).

Deadlines are engineering defaults for the incident team, not legal advice; counsel confirms
which notices apply (see docs/compliance/incident-response-runbook.md). Each hospital's country
decides the set. Any signed-in person can report; only compliance staff see the log.

"Without delay" notices (India) get a short working deadline of 24 hours so they show as urgent.
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import AuditAction, record_audit_event
from apps.notifications.services import send_email
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError

from .models import IncidentNotification, SecurityIncident

Kind = IncidentNotification.Kind
NotifyStatus = IncidentNotification.Status
Status = SecurityIncident.Status

HIPAA_LARGE_BREACH = 500
ALERT_BEFORE = timedelta(hours=24)
# Order of an incident's life; a closed incident cannot reopen (report a new one).
_NEXT = {
    Status.REPORTED: {Status.INVESTIGATING, Status.CONTAINED, Status.CLOSED},
    Status.INVESTIGATING: {Status.CONTAINED, Status.CLOSED},
    Status.CONTAINED: {Status.INVESTIGATING, Status.CLOSED},
    Status.CLOSED: set(),
}


def _country() -> str:
    from apps.organizations.models import Organization

    organization = Organization.objects.only("country").first()
    return organization.country if organization else ""


def required_deadlines(incident: SecurityIncident, country: str) -> dict[str, datetime]:
    """Which notices this incident needs and when each is due."""
    start = incident.detected_at
    due: dict[str, datetime] = {}
    if country == "IN":
        due[Kind.CERT_IN] = start + timedelta(hours=6)
        if incident.personal_data_affected:
            due[Kind.DPDP_BOARD_INITIAL] = start + timedelta(hours=24)
            due[Kind.DPDP_BOARD_DETAILED] = start + timedelta(hours=72)
            due[Kind.DPDP_PEOPLE] = start + timedelta(hours=24)
    elif country == "US" and incident.personal_data_affected:
        sixty_days = start + timedelta(days=60)
        due[Kind.HIPAA_INDIVIDUALS] = sixty_days
        people = incident.people_affected
        if people is not None and people < HIPAA_LARGE_BREACH:
            year_end = datetime(start.year + 1, 1, 1, tzinfo=start.tzinfo)
            due[Kind.HIPAA_HHS] = year_end + timedelta(days=60)
        else:  # unknown numbers are treated as the large, earlier deadline
            due[Kind.HIPAA_HHS] = sixty_days
        if people is not None and people > HIPAA_LARGE_BREACH:
            due[Kind.HIPAA_MEDIA] = sixty_days
    return due


def _sync_notifications(incident: SecurityIncident) -> None:
    """Add missing notices and move pending deadlines when the facts change. Done notices stay."""
    due = required_deadlines(incident, _country())
    for kind, due_at in due.items():
        row, created = IncidentNotification.objects.get_or_create(
            incident=incident, kind=kind, defaults={"due_at": due_at}
        )
        if not created and row.status == NotifyStatus.PENDING and row.due_at != due_at:
            row.due_at = due_at
            row.soon_alert_sent_at = None
            row.overdue_alert_sent_at = None
            row.save()
    # A notice no longer required by the facts is kept visible, for a person to close.


def compliance_team_emails() -> list[str]:
    from apps.access_control.catalog import P
    from apps.access_control.models import RoleAssignment

    now = timezone.now()
    emails = (
        RoleAssignment.objects.filter(
            Q(valid_until__isnull=True) | Q(valid_until__gt=now),
            revoked_at__isnull=True,
            valid_from__lte=now,
            user__is_active=True,
            role__role_permissions__permission__codename=P.COMPLIANCE_MANAGE,
        )
        .values_list("user__email", flat=True)
        .distinct()
    )
    return sorted(set(emails))


def _link(incident: SecurityIncident) -> str:
    return f"{settings.HIMS_APP_BASE_URL.rstrip('/')}/compliance?incident={incident.pk}"


def _alert_reported(incident: SecurityIncident) -> None:
    """No incident details in the email: the link needs a sign-in (spec 13.3)."""
    deadlines = "\n".join(
        f"- {row.get_kind_display()}: {timezone.localtime(row.due_at):%d %b %Y %H:%M %Z}"
        for row in incident.notifications.all()
    )
    send_email(
        to=compliance_team_emails(),
        subject="HIMS: security incident reported",
        body=(
            f"A security incident was reported ({incident.get_severity_display()} severity).\n\n"
            + (f"Deadlines:\n{deadlines}\n\n" if deadlines else "")
            + f"See it here (sign-in needed): {_link(incident)}\n"
        ),
        category="compliance",
        template="compliance.incident_reported",
        related=("security_incident", incident.pk),
    )


@transaction.atomic
def report_incident(*, actor, title, description, request=None, **fields) -> SecurityIncident:
    incident = SecurityIncident.objects.create(
        title=title, description=description, reported_by=actor, **fields
    )
    _sync_notifications(incident)
    record_audit_event(
        action=AuditAction.COMPLIANCE_INCIDENT_REPORTED,
        resource_type="security_incident",
        resource_id=incident.pk,
        actor=actor,
        request=request,
        metadata={"severity": incident.severity},
    )
    transaction.on_commit(lambda: _alert_reported(incident))
    return incident


@transaction.atomic
def update_incident(*, actor, incident_id, version, request=None, **changes) -> SecurityIncident:
    incident = lock_for_update(SecurityIncident, pk=incident_id, expected_version=version)
    if incident.status == Status.CLOSED:
        raise ConflictError("A closed incident cannot change. Report a new one.", code="CLOSED")
    new_status = changes.pop("status", None)
    before = {name: str(getattr(incident, name)) for name in changes}
    for name, value in changes.items():
        setattr(incident, name, value)
    if new_status and new_status != incident.status:
        if new_status not in _NEXT[incident.status]:
            raise ConflictError("This status change is not allowed.", code="INVALID_TRANSITION")
        before["status"] = incident.status
        changes["status"] = new_status
        incident.status = new_status
    if incident.occurred_at and incident.occurred_at > incident.detected_at:
        raise ConflictError("It cannot have happened after it was noticed.", code="INVALID_DATES")
    _sync_notifications(incident)
    if incident.status == Status.CLOSED:
        if not incident.closure_summary.strip():
            raise ConflictError("Write a closure summary first.", code="SUMMARY_REQUIRED")
        if incident.notifications.filter(status=NotifyStatus.PENDING).exists():
            raise ConflictError(
                "Finish every notification (done or not required) before closing.",
                code="NOTIFICATIONS_PENDING",
            )
        incident.closed_at = timezone.now()
    bump_version(incident)
    incident.save()
    record_audit_event(
        action=AuditAction.COMPLIANCE_INCIDENT_UPDATED,
        resource_type="security_incident",
        resource_id=incident.pk,
        actor=actor,
        request=request,
        changes={
            "before": before,
            "after": {name: str(getattr(incident, name)) for name in before},
        },
    )
    return incident


@transaction.atomic
def record_notification(
    *, actor, notification_id, status: str, reference="", note="", request=None
) -> IncidentNotification:
    row = IncidentNotification.objects.select_for_update().get(pk=notification_id)
    if row.status != NotifyStatus.PENDING:
        raise ConflictError("This notification is already recorded.", code="ALREADY_RECORDED")
    if status == NotifyStatus.NOT_REQUIRED and not note.strip():
        raise ConflictError("Say why it is not required.", code="REASON_REQUIRED")
    row.status = status
    row.reference = reference
    row.note = note
    row.done_at = timezone.now()
    row.done_by = actor
    row.save()
    record_audit_event(
        action=AuditAction.COMPLIANCE_NOTIFICATION_RECORDED,
        resource_type="security_incident",
        resource_id=row.incident_id,
        actor=actor,
        request=request,
        reason=note,
        metadata={"kind": row.kind, "status": status, "late": row.done_at > row.due_at},
    )
    return row


def send_deadline_alerts(now=None) -> int:
    """Hourly: warn the compliance team once when a notice is due within 24 hours and once when
    it is overdue. Safe to run repeatedly. Returns how many alerts were sent."""
    now = now or timezone.now()
    sent = 0
    pending = IncidentNotification.objects.filter(status=NotifyStatus.PENDING).select_related(
        "incident"
    )
    for row in pending.filter(overdue_alert_sent_at__isnull=True, due_at__lte=now):
        _alert_deadline(row, "is overdue")
        row.overdue_alert_sent_at = now
        row.save(update_fields=["overdue_alert_sent_at", "updated_at"])
        sent += 1
    for row in pending.filter(
        soon_alert_sent_at__isnull=True, due_at__gt=now, due_at__lte=now + ALERT_BEFORE
    ):
        _alert_deadline(row, "is due within 24 hours")
        row.soon_alert_sent_at = now
        row.save(update_fields=["soon_alert_sent_at", "updated_at"])
        sent += 1
    return sent


def _alert_deadline(row: IncidentNotification, state: str) -> None:
    send_email(
        to=compliance_team_emails(),
        subject=f"HIMS: {row.get_kind_display()} {state}",
        body=(
            f"{row.get_kind_display()} {state} "
            f"(deadline {timezone.localtime(row.due_at):%d %b %Y %H:%M %Z}).\n\n"
            f"See the incident (sign-in needed): {_link(row.incident)}\n"
        ),
        category="compliance",
        template="compliance.incident_deadline",
        related=("security_incident", row.incident_id),
    )
