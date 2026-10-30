"""Licence expiry: who is affected and the daily alert emails (HIMS-STAFF-006).

The daily job finds licences that have reached an alert stage (by default 60, 30 and 7 days
before expiry, and once expired) and emails HR (people who verify credentials or manage staff)
and the person themselves. Each stage is sent once per licence and expiry date, so running the
job twice, or after a missed day, never repeats or skips an alert (spec 14.3).
"""

from datetime import date, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import AuditAction, record_audit_event
from apps.notifications.services import send_email

from .models import CredentialExpiryAlert, StaffCredential, StaffMember, VerificationStatus

WORKING = (StaffMember.EmploymentStatus.ACTIVE, StaffMember.EmploymentStatus.ON_LEAVE)


def alert_days() -> list[int]:
    return sorted({int(d) for d in settings.HIMS_CREDENTIAL_ALERT_DAYS if int(d) > 0}, reverse=True)


def watched_credentials(today: date | None = None, within_days: int | None = None):
    """Licences of working staff that are expired or expire within the window, soonest first.

    Rejected licences are left out (they are already known to be invalid)."""
    today = today or timezone.localdate()
    window = within_days if within_days is not None else max(alert_days(), default=60)
    return (
        StaffCredential.objects.filter(
            expires_at__isnull=False,
            expires_at__lte=today + timedelta(days=window),
            staff__employment_status__in=WORKING,
        )
        .exclude(verification_status=VerificationStatus.REJECTED)
        .select_related("staff", "staff__user")
        .order_by("expires_at", "staff__family_name")
    )


def stage_for(expires_at: date, today: date) -> int | None:
    """The alert stage reached today: 0 once expired, else the smallest configured number of
    days that is at least the days left (e.g. 25 days left -> the 30-day stage)."""
    days_left = (expires_at - today).days
    if days_left < 0:
        return 0
    reached = [d for d in alert_days() if days_left <= d]
    return min(reached) if reached else None


def hr_recipients() -> list[str]:
    """Active people who verify credentials or manage staff (organization-wide)."""
    from apps.access_control.catalog import P
    from apps.access_control.models import RoleAssignment

    now = timezone.now()
    users = (
        RoleAssignment.objects.filter(
            Q(valid_until__isnull=True) | Q(valid_until__gt=now),
            revoked_at__isnull=True,
            valid_from__lte=now,
            user__is_active=True,
            role__role_permissions__permission__codename__in=[
                P.STAFF_CREDENTIALS_VERIFY,
                P.STAFF_MANAGE,
            ],
        )
        .values_list("user__email", flat=True)
        .distinct()
    )
    return sorted(set(users))


def _describe(credential: StaffCredential, stage: int) -> str:
    staff = credential.staff
    when = credential.expires_at.strftime("%d %b %Y")
    status = f"EXPIRED on {when}" if stage == 0 else f"expires on {when}"
    return (
        f"- {staff.given_name} {staff.family_name} ({staff.employee_number}): "
        f"{credential.get_credential_type_display()} {credential.registration_number}, "
        f"{credential.issuing_authority} - {status}"
    )


def send_credential_expiry_alerts(today: date | None = None) -> int:
    """Send every alert that is due. Returns how many licence alerts were sent."""
    today = today or timezone.localdate()
    hospital = _hospital_name()
    hr = hr_recipients()
    sent_lines: list[str] = []
    for credential in watched_credentials(today):
        stage = stage_for(credential.expires_at, today)
        if stage is None:
            continue
        line = _send_one(credential, stage, hr, hospital)
        if line:
            sent_lines.append(line)
    if sent_lines and hr:
        send_email(
            subject=f"{hospital}: {len(sent_lines)} licence(s) expiring or expired",
            body=(
                "These staff licences need attention (renewal or a new copy):\n\n"
                + "\n".join(sent_lines)
                + "\n\nSee the Licence expiry page in HIMS for the full list.\n"
            ),
            to=hr,
            category="staff",
            template="staff.licence_expiry_hr",
        )
    return len(sent_lines)


def _send_one(credential, stage: int, hr: list[str], hospital: str) -> str | None:
    """Record the alert first (once only), then email the person. Returns the HR summary line,
    or None when this stage was already sent."""
    try:
        with transaction.atomic():
            alert = CredentialExpiryAlert.objects.create(
                credential=credential,
                days_before=stage,
                expires_at=credential.expires_at,
                recipients=len(hr),
            )
            record_audit_event(
                action=AuditAction.CREDENTIAL_EXPIRY_ALERT_SENT,
                resource_type="staff_credential",
                resource_id=credential.pk,
                organization_id=credential.organization_id,
                metadata={
                    "stage": "expired" if stage == 0 else f"{stage} days before",
                    "expires_at": credential.expires_at.isoformat(),
                    "hr_recipients": len(hr),
                },
            )
    except IntegrityError:
        return None  # already sent for this stage
    person = credential.staff.user
    if person is not None and person.is_active:
        when = credential.expires_at.strftime("%d %b %Y")
        what = f"{credential.get_credential_type_display()} {credential.registration_number}"
        send_email(
            subject=f"{hospital}: your licence {'has expired' if stage == 0 else 'expires soon'}",
            body=(
                f"Hello {credential.staff.given_name},\n\n"
                f"Your {what} ({credential.issuing_authority}) "
                f"{'expired on' if stage == 0 else 'expires on'} {when}.\n"
                "Please renew it and give a copy of the new licence to HR.\n"
            ),
            to=[person.email],
            category="staff",
            template="staff.licence_expiry_person",
        )
        alert.recipients += 1
        alert.save(update_fields=["recipients"])
    return _describe(credential, stage)


def _hospital_name() -> str:
    from apps.organizations.models import Organization

    organization = Organization.objects.only("display_name").first()
    return organization.display_name if organization else "HIMS"
