"""Audit recording (spec 13.4, ADR-008).

Call ``record_audit_event`` inside the same transaction as the change it describes so that the
audit row commits or rolls back with it. Access denials are recorded by the API exception
handler, outside the rolled-back transaction.
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.db import models
from django.db.models.fields.files import FieldFile

from common.client_ip import client_ip
from common.request_context import get_request_id

from .models import AuditEvent

logger = logging.getLogger(__name__)

REDACTED = "[REDACTED]"
# Field names whose values are never written into audit change sets.
SENSITIVE_FIELDS = frozenset({"password", "token", "secret", "otp", "mfa_secret"})


class AuditAction:
    ORGANIZATION_PROVISIONED = "organization.provisioned"
    ORGANIZATION_UPDATED = "organization.updated"
    FACILITY_CREATED = "facility.created"
    FACILITY_UPDATED = "facility.updated"
    DEPARTMENT_CREATED = "department.created"
    DEPARTMENT_UPDATED = "department.updated"
    DEPARTMENT_HOURS_CHANGED = "department.hours.changed"
    DEPARTMENT_SERVICE_CREATED = "department.service.created"
    DEPARTMENT_SERVICE_UPDATED = "department.service.updated"
    CATALOG_ITEM_CREATED = "staff.catalog.created"
    CATALOG_ITEM_UPDATED = "staff.catalog.updated"
    LOCATION_CREATED = "location.created"
    LOCATION_UPDATED = "location.updated"
    BED_STATUS_CHANGED = "bed.status.changed"
    UPLOAD_BLOCKED = "upload.blocked"
    STAFF_DOCUMENT_VIRUS_FOUND = "staff.document.virus_found"
    STAFF_DOCUMENTS_SCANNED = "staff.documents.scanned"
    STAFF_PRIVILEGE_GRANTED = "staff.privilege.granted"
    STAFF_PRIVILEGE_ENDED = "staff.privilege.ended"
    STAFFING_REQUIREMENT_CREATED = "rota.staffing_requirement.created"
    STAFFING_REQUIREMENT_UPDATED = "rota.staffing_requirement.updated"
    STAFFING_GAP_ALERT_SENT = "rota.staffing_gap_alert.sent"
    LEAVE_ENTITLEMENT_CREATED = "leave.entitlement.created"
    LEAVE_ENTITLEMENT_UPDATED = "leave.entitlement.updated"
    LEAVE_BALANCE_ADJUSTED = "leave.balance.adjusted"
    EQUIPMENT_CREATED = "equipment.created"
    EQUIPMENT_UPDATED = "equipment.updated"
    EQUIPMENT_STATUS_CHANGED = "equipment.status.changed"
    EQUIPMENT_SERVICE_RECORDED = "equipment.service.recorded"
    ORGANIZATION_LOGO_CHANGED = "organization.logo.changed"
    MESSAGE_TEMPLATE_UPDATED = "notification.template.updated"
    MESSAGE_TEMPLATE_RESET = "notification.template.reset"
    NUMBERING_SCHEME_CREATED = "numbering.scheme.created"
    NUMBERING_SCHEME_UPDATED = "numbering.scheme.updated"
    NUMBERING_NEXT_NUMBER_SET = "numbering.next_number.set"
    FEATURE_FLAG_CHANGED = "feature.flag.changed"
    FEATURE_CATALOG_SYNCED = "feature.catalog.synced"
    USER_CREATED = "user.created"
    ACCOUNT_CREATED = "user.account.created"
    ACCOUNT_DEACTIVATED = "user.account.deactivated"
    ACCOUNT_REACTIVATED = "user.account.reactivated"
    USER_INVITATION_ISSUED = "user.invitation.issued"
    USER_INVITATION_ACCEPTED = "user.invitation.accepted"
    USER_INVITATION_REJECTED = "user.invitation.rejected"
    PASSWORD_RESET_REQUESTED = "user.password_reset.requested"  # noqa: S105 - event name
    PASSWORD_RESET_COMPLETED = "user.password_reset.completed"  # noqa: S105 - event name
    PASSWORD_RESET_REJECTED = "user.password_reset.rejected"  # noqa: S105 - event name
    AUTH_LOGIN = "auth.login"
    AUTH_LOGIN_FAILED = "auth.login_failed"
    AUTH_LOGOUT = "auth.logout"
    AUTH_SESSIONS_ENDED = "auth.sessions.ended"
    AUTH_CONSOLE_ADDRESS_REFUSED = "auth.console_address_refused"
    ACCESS_REVIEW_STARTED = "access.review.started"
    ACCESS_REVIEW_DECIDED = "access.review.decided"
    ACCESS_REVIEW_COMPLETED = "access.review.completed"
    ACCESS_REVIEW_CANCELLED = "access.review.cancelled"
    ACCESS_REVIEW_EXPORTED = "access.review.exported"
    ACCESS_REVIEW_REMINDER_SENT = "access.review.reminder_sent"
    ACCESS_DELEGATION_CREATED = "access.delegation.created"
    ACCESS_DELEGATION_ENDED = "access.delegation.ended"
    SUPPORT_ACCESS_REQUESTED = "support.access.requested"
    SUPPORT_ACCESS_APPROVED = "support.access.approved"
    SUPPORT_ACCESS_REFUSED = "support.access.refused"
    SUPPORT_ACCESS_CANCELLED = "support.access.cancelled"
    SUPPORT_ACCESS_EMERGENCY_OPENED = "support.access.emergency_opened"
    SUPPORT_ACCESS_ENDED = "support.access.ended"
    SUPPORT_ACCESS_USED = "support.access.used"
    AUTH_IDENTITY_CONFIRMED = "auth.identity_confirmed"
    AUTH_IDENTITY_CONFIRM_FAILED = "auth.identity_confirm_failed"
    AUTH_IDENTITY_CONFIRM_LOCKED = "auth.identity_confirm_locked"
    AUTH_MFA_ENABLED = "auth.mfa.enabled"
    AUTH_MFA_DISABLED = "auth.mfa.disabled"
    AUTH_MFA_RESET = "auth.mfa.reset"
    AUTH_MFA_VERIFIED = "auth.mfa.verified"
    AUTH_MFA_FAILED = "auth.mfa.failed"
    AUTH_MFA_RECOVERY_CODE_USED = "auth.mfa.recovery_code_used"
    AUTH_MFA_RECOVERY_CODES_REGENERATED = "auth.mfa.recovery_codes_regenerated"
    AUTH_PASSKEY_ADDED = "auth.passkey.added"
    AUTH_PASSKEY_REMOVED = "auth.passkey.removed"
    ROLE_CREATED = "access.role.created"
    ROLE_UPDATED = "access.role.updated"
    ROLE_ASSIGNED = "access.role.assigned"
    ROLE_REVOKED = "access.role.revoked"
    ACCESS_DENIED = "access.denied"
    ACCESS_NONE_ASSIGNED = "access.none_assigned"
    STAFF_CREATED = "staff.member.created"
    STAFF_UPDATED = "staff.member.updated"
    STAFF_DEPARTMENT_ASSIGNED = "staff.department.assigned"
    STAFF_QUALIFICATION_ADDED = "staff.qualification.added"
    STAFF_QUALIFICATION_VERIFIED = "staff.qualification.verified"
    STAFF_DEPARTMENT_ASSIGNMENT_ENDED = "staff.department.assignment_ended"
    STAFF_CREDENTIAL_ADDED = "staff.credential.added"
    STAFF_CREDENTIAL_VERIFIED = "staff.credential.verified"
    STAFF_DOCUMENT_UPLOADED = "staff.document.uploaded"
    STAFF_DOCUMENT_DOWNLOADED = "staff.document.downloaded"
    STAFF_DOCUMENT_ARCHIVED = "staff.document.archived"
    SHIFT_TYPE_CREATED = "rota.shift_type.created"
    SHIFT_TYPE_UPDATED = "rota.shift_type.updated"
    SHIFT_ADDED = "rota.shift.added"
    SHIFT_CANCELLED = "rota.shift.cancelled"
    LEAVE_REQUESTED = "leave.requested"
    LEAVE_APPROVED = "leave.approved"
    LEAVE_REJECTED = "leave.rejected"
    LEAVE_CANCELLED = "leave.cancelled"
    CREDENTIAL_EXPIRY_ALERT_SENT = "staff.credential.expiry_alert_sent"
    AUDIT_SEARCHED = "audit.events.searched"
    AUDIT_EXPORTED = "audit.events.exported"
    COMPLIANCE_REQUIREMENT_UPDATED = "compliance.requirement.updated"
    COMPLIANCE_RISK_CREATED = "compliance.risk.created"
    COMPLIANCE_RISK_UPDATED = "compliance.risk.updated"
    COMPLIANCE_INCIDENT_REPORTED = "compliance.incident.reported"
    COMPLIANCE_INCIDENT_UPDATED = "compliance.incident.updated"
    COMPLIANCE_NOTIFICATION_RECORDED = "compliance.incident.notification_recorded"
    COMPLIANCE_BROWSER_REPORT_REVIEWED = "compliance.browser_report.reviewed"
    COMPLIANCE_CONSOLE_BLOCK_REVIEWED = "compliance.console_block.reviewed"
    RETENTION_PERIOD_CHANGED = "compliance.retention.period_changed"
    RETENTION_PERIOD_APPLIED = "compliance.retention.period_applied"
    RETENTION_PURGE_RUN = "compliance.retention.purge_run"
    LEGAL_HOLD_PLACED = "compliance.legal_hold.placed"
    LEGAL_HOLD_RELEASED = "compliance.legal_hold.released"
    NOTIFICATION_RETRIED = "notification.retried"
    NOTIFICATION_TEST_SENT = "notification.test_sent"
    AUDIT_INTEGRITY_CHECKED = "audit.integrity.checked"
    AUDIT_INTEGRITY_ALERT_SENT = "audit.integrity.alert_sent"
    BACKUP_CREATED = "recovery.backup.created"
    RESTORE_DRILL_COMPLETED = "recovery.restore_drill.completed"
    PERFORMANCE_CHECK_RUN = "performance.check_run"
    DATABASE_USERS_SET_UP = "database.users_set_up"
    DATABASE_ENCRYPTION_ROTATED = "database.encryption_rotated"
    OUTBOX_CLEANED_UP = "outbox.cleaned_up"
    OUTBOX_EVENT_SENT_AGAIN = "outbox.event_sent_again"
    OUTBOX_EVENT_DISMISSED = "outbox.event_dismissed"
    # Patients (HIMS-PAT-001). Reading a record is audited too (spec 13.4).
    PATIENT_REGISTERED = "patient.registered"
    PATIENT_UPDATED = "patient.updated"
    PATIENT_RECORD_VIEWED = "patient.record.viewed"
    PATIENT_LIST_SEARCHED = "patient.searched"
    PATIENT_CONTACT_ADDED = "patient.contact.added"
    PATIENT_CONTACT_UPDATED = "patient.contact.updated"
    PATIENT_RELATIONSHIP_ADDED = "patient.relationship.added"
    PATIENT_RELATIONSHIP_UPDATED = "patient.relationship.updated"
    PATIENT_IDENTIFIER_ADDED = "patient.identifier.added"
    PATIENT_IDENTIFIER_ENDED = "patient.identifier.ended"
    PATIENT_CONSENT_RECORDED = "patient.consent.recorded"


def _jsonable(value):
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, FieldFile):
        return value.name or ""  # the stored path, never the file's content
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, models.Model):
        return str(value.pk)
    return value


def snapshot(instance: models.Model, fields=None) -> dict:
    """Plain-value snapshot of concrete fields, with sensitive values redacted."""
    result = {}
    for field in instance._meta.concrete_fields:
        if fields is not None and field.name not in fields:
            continue
        name = field.attname
        if field.name in SENSITIVE_FIELDS:
            result[field.name] = REDACTED
        else:
            result[field.name] = _jsonable(getattr(instance, name))
    return result


def model_changes(before: dict, after: dict) -> dict:
    changed = sorted(key for key in after if before.get(key) != after.get(key))
    return {
        "before": {key: before.get(key) for key in changed},
        "after": {key: after.get(key) for key in changed},
    }


def record_audit_event(
    *,
    action: str,
    resource_type: str,
    resource_id="",
    actor=None,
    request=None,
    outcome: str = AuditEvent.Outcome.SUCCESS,
    organization_id=None,
    facility_id=None,
    changes: dict | None = None,
    metadata: dict | None = None,
    reason: str = "",
) -> AuditEvent:
    if actor is None and request is not None:
        user = getattr(request, "user", None)
        actor = user if user is not None and user.is_authenticated else None

    if organization_id is None:
        from django.conf import settings

        from apps.organizations.models import Organization

        organization_id = (
            Organization.objects.filter(deployment_id=settings.HIMS_DEPLOYMENT_ID)
            .values_list("pk", flat=True)
            .first()
        )

    if actor is not None:
        actor_type = AuditEvent.ActorType.USER
    elif request is not None:
        actor_type = AuditEvent.ActorType.ANONYMOUS
    else:
        actor_type = AuditEvent.ActorType.SYSTEM

    return AuditEvent.objects.create(
        organization_id=organization_id,
        facility_id=facility_id,
        actor_type=actor_type,
        actor_id=actor.pk if actor else None,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id or ""),
        outcome=outcome,
        reason=reason,
        request_id=get_request_id() or "",
        ip_address=client_ip(request) if request is not None else None,
        user_agent=(request.headers.get("User-Agent", "")[:512] if request is not None else ""),
        changes=changes or {},
        metadata=metadata or {},
    )
