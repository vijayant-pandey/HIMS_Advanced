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
    LOCATION_CREATED = "location.created"
    LOCATION_UPDATED = "location.updated"
    BED_STATUS_CHANGED = "bed.status.changed"
    NUMBERING_SCHEME_CREATED = "numbering.scheme.created"
    NUMBERING_SCHEME_UPDATED = "numbering.scheme.updated"
    NUMBERING_NEXT_NUMBER_SET = "numbering.next_number.set"
    USER_CREATED = "user.created"
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
    AUTH_MFA_ENABLED = "auth.mfa.enabled"
    AUTH_MFA_DISABLED = "auth.mfa.disabled"
    AUTH_MFA_RESET = "auth.mfa.reset"
    AUTH_MFA_VERIFIED = "auth.mfa.verified"
    AUTH_MFA_FAILED = "auth.mfa.failed"
    AUTH_MFA_RECOVERY_CODE_USED = "auth.mfa.recovery_code_used"
    AUTH_MFA_RECOVERY_CODES_REGENERATED = "auth.mfa.recovery_codes_regenerated"
    ROLE_CREATED = "access.role.created"
    ROLE_ASSIGNED = "access.role.assigned"
    ROLE_REVOKED = "access.role.revoked"
    ACCESS_DENIED = "access.denied"
    ACCESS_NONE_ASSIGNED = "access.none_assigned"
    STAFF_CREATED = "staff.member.created"
    STAFF_UPDATED = "staff.member.updated"
    STAFF_DEPARTMENT_ASSIGNED = "staff.department.assigned"
    STAFF_QUALIFICATION_ADDED = "staff.qualification.added"
    STAFF_CREDENTIAL_ADDED = "staff.credential.added"
    STAFF_CREDENTIAL_VERIFIED = "staff.credential.verified"
    AUDIT_SEARCHED = "audit.events.searched"


def _jsonable(value):
    if isinstance(value, (UUID, Decimal)):
        return str(value)
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


def _client_ip(request) -> str | None:
    # TODO(HIMS-SEC-014): trust X-Forwarded-For only from the ALB once the network is defined.
    return request.META.get("REMOTE_ADDR") or None


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
        ip_address=_client_ip(request) if request is not None else None,
        user_agent=(request.headers.get("User-Agent", "")[:512] if request is not None else ""),
        changes=changes or {},
        metadata=metadata or {},
    )
