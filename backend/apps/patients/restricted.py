"""Restricted records and emergency access (HIMS-PAT-006; spec 4.5, 13.4; D14, D23).

Rules: docs/p0/phase-2-patients/04-roles-and-permissions.md ("Restricted records (D23) need
``patients.restricted`` or emergency access") and 03-state-machines.md ("Emergency access").

* Medical records restrict a VIP's or a staff member's record (``patients.restricted``), with a
  reason. From then on it is hidden from patient search (an exact MRN shows only that a restricted
  record exists) and opening it is refused, except for people who hold ``patients.restricted``
  and people with emergency access to it.
* Emergency access (``clinical.emergency_access``: doctors and nurses) opens one restricted record
  for 4 hours, with a reason of at least 10 characters. Medical records are emailed at once (no
  patient details, no reason). The person may end it early.
* After it has ended, someone from medical records other than the person who used it reviews it
  (``patients.records_correct``): appropriate, or not appropriate with a note.
* Every opening of a restricted record is audited with ``restricted`` in its metadata, so
  medical records can list them (``restricted_openings``).
"""

from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.access_control.catalog import P
from apps.access_control.models import RoleAssignment
from apps.access_control.selectors import get_permission_scope
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction, record_audit_event
from apps.notifications.services import send_message
from apps.organizations.dates import hospital_time
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError, ScopeViolation

from .models import EmergencyAccess, Patient

EMERGENCY_HOURS = 4
MIN_REASON = 10
Outcome = EmergencyAccess.Outcome


class RestrictedRecord(ScopeViolation):
    code = "RESTRICTED_RECORD"
    title = "Restricted record"


class State:
    ACTIVE = "active"
    TO_REVIEW = "to_review"
    REVIEWED = "reviewed"
    CHOICES = (
        (ACTIVE, "Open now"),
        (TO_REVIEW, "Ended, to review"),
        (REVIEWED, "Reviewed"),
    )


def _holds(user, codename: str) -> bool:
    """Patients belong to the whole hospital: a grant anywhere counts (like patient search)."""
    return not get_permission_scope(user, codename).is_empty


def may_see_restricted(user) -> bool:
    return _holds(user, P.PATIENTS_RESTRICTED)


def may_use_emergency_access(user) -> bool:
    return _holds(user, P.EMERGENCY_ACCESS)


def may_review_emergency_access(user) -> bool:
    return _holds(user, P.PATIENTS_RECORDS_CORRECT)


def _active_filter(now=None) -> Q:
    now = now or timezone.now()
    return Q(ended_at__isnull=True, expires_at__gt=now)


def in_state(queryset, state: str):
    """Emergency access in one state: open now, ended and waiting for review, or reviewed."""
    if state == State.ACTIVE:
        return queryset.filter(_active_filter())
    if state == State.TO_REVIEW:
        return queryset.filter(reviewed_at__isnull=True).exclude(_active_filter())
    if state == State.REVIEWED:
        return queryset.filter(reviewed_at__isnull=False)
    return queryset


def state_of(access: EmergencyAccess) -> str:
    if access.reviewed_at:
        return State.REVIEWED
    if access.ended_at is None and access.expires_at > timezone.now():
        return State.ACTIVE
    return State.TO_REVIEW


def active_access(user, patient_id) -> EmergencyAccess | None:
    if not getattr(user, "is_authenticated", False):
        return None
    return (
        EmergencyAccess.objects.filter(_active_filter(), user=user, patient_id=patient_id)
        .order_by("-expires_at")
        .first()
    )


@dataclass(frozen=True)
class Opening:
    """How someone may open this record: what goes in the audit of the opening, and the
    emergency access used (if any)."""

    metadata: dict = field(default_factory=dict)
    access: EmergencyAccess | None = None


def opening(user, patient: Patient) -> Opening:
    """Raise RestrictedRecord unless the user may open this (restricted) record."""
    if not patient.is_restricted:
        return Opening()
    if may_see_restricted(user):
        return Opening({"restricted": True, "via": "restricted_permission"})
    access = active_access(user, patient.pk)
    if access is not None:
        return Opening(
            {"restricted": True, "via": "emergency_access", "emergency_access": str(access.pk)},
            access,
        )
    raise RestrictedRecord(
        "This is a restricted record. Medical records can open it; in an emergency a doctor or "
        "nurse can open it with emergency access."
    )


def _reason(text: str, field_name: str = "reason") -> str:
    text = " ".join((text or "").split())
    if len(text) < MIN_REASON:
        raise ValidationError({field_name: f"Give the reason (at least {MIN_REASON} characters)."})
    return text


def _audit(action, patient, *, actor, request, reason="", changes=None, metadata=None):
    record_audit_event(
        action=action,
        resource_type="patient",
        resource_id=patient.pk,
        facility_id=patient.registered_facility_id,
        actor=actor,
        request=request,
        reason=reason,
        changes=changes or {},
        metadata=metadata or {},
    )


@transaction.atomic
def set_restriction(
    *,
    actor,
    patient_id,
    version: int,
    restricted: bool,
    restriction: str = "",
    reason: str,
    request=None,
) -> Patient:
    """Restrict a record (VIP, staff, other) or lift the restriction; a reason is required."""
    if actor is not None and not may_see_restricted(actor):
        raise ScopeViolation("Only medical records can restrict a record or lift the restriction.")
    patient = lock_for_update(Patient, pk=patient_id, expected_version=version)
    reason = _reason(reason)
    if restricted and restriction not in Patient.Restriction.values:
        raise ValidationError({"restriction": "Say why: VIP, member of staff or other."})
    if not restricted:
        restriction = ""
    if (patient.is_restricted, patient.restriction) == (restricted, restriction):
        return patient
    before = {"is_restricted": patient.is_restricted, "restriction": patient.restriction}
    patient.is_restricted, patient.restriction = restricted, restriction
    bump_version(patient)
    patient.save(update_fields=["is_restricted", "restriction", "version", "updated_at"])
    _audit(
        AuditAction.PATIENT_RESTRICTED if restricted else AuditAction.PATIENT_RESTRICTION_LIFTED,
        patient,
        actor=actor,
        request=request,
        reason=reason,
        changes={
            "before": before,
            "after": {"is_restricted": restricted, "restriction": restriction},
        },
    )
    return patient


def _when(moment) -> str:
    return hospital_time(moment).strftime("%d %b %Y %H:%M %Z")


def reviewer_emails() -> list[str]:
    """Medical records who review emergency access (``patients.records_correct``)."""
    now = timezone.now()
    emails = (
        RoleAssignment.objects.filter(
            Q(valid_until__isnull=True) | Q(valid_until__gt=now),
            revoked_at__isnull=True,
            valid_from__lte=now,
            user__is_active=True,
            support_access__isnull=True,
            role__role_permissions__permission__codename=P.PATIENTS_RECORDS_CORRECT,
        )
        .values_list("user__email", flat=True)
        .distinct()
    )
    return sorted({email for email in emails if email})


def _review_link() -> str:
    return f"{settings.HIMS_APP_BASE_URL.rstrip('/')}/patients/emergency-access"


@transaction.atomic
def open_emergency_access(*, actor, patient_id, reason: str, request=None) -> EmergencyAccess:
    """Open a restricted record for 4 hours (D14). Medical records are emailed at once."""
    if not may_use_emergency_access(actor):
        raise ScopeViolation("Your role cannot use emergency access.")
    patient = Patient.objects.select_for_update().get(pk=patient_id)
    if not patient.is_restricted or may_see_restricted(actor):
        raise ConflictError(
            "You can open this record without emergency access.", code="EMERGENCY_ACCESS_NOT_NEEDED"
        )
    current = active_access(actor, patient.pk)
    if current is not None:
        raise ConflictError(
            f"You already have emergency access to this record until {_when(current.expires_at)}.",
            code="EMERGENCY_ACCESS_OPEN",
        )
    reason = _reason(reason)
    now = timezone.now()
    access = EmergencyAccess.objects.create(
        organization_id=patient.organization_id,
        patient=patient,
        user=actor,
        reason=reason,
        expires_at=now + timedelta(hours=EMERGENCY_HOURS),
    )
    _audit(
        AuditAction.EMERGENCY_ACCESS_OPENED,
        patient,
        actor=actor,
        request=request,
        reason=reason,
        metadata={"emergency_access": str(access.pk), "hours": EMERGENCY_HOURS},
    )
    values = {
        "name": actor.display_name or actor.email,
        "opened": _when(now),
        "until": _when(access.expires_at),
        "link": _review_link(),
    }

    def tell_medical_records():
        recipients = [email for email in reviewer_emails() if email != actor.email]
        if recipients:
            send_message("patients.emergency_access_opened", to=recipients, values=values)

    transaction.on_commit(tell_medical_records)
    return access


@transaction.atomic
def end_emergency_access(*, actor, patient_id, request=None) -> EmergencyAccess:
    """The person who opened it ends it early (done with the record)."""
    current = active_access(actor, patient_id)
    if current is None:
        raise ConflictError("You have no emergency access to this record.", code="NOT_OPEN")
    access = EmergencyAccess.objects.select_for_update().get(pk=current.pk)
    access.ended_at = timezone.now()
    bump_version(access)
    access.save(update_fields=["ended_at", "version", "updated_at"])
    _audit(
        AuditAction.EMERGENCY_ACCESS_ENDED,
        access.patient,
        actor=actor,
        request=request,
        metadata={"emergency_access": str(access.pk)},
    )
    return access


@transaction.atomic
def review_emergency_access(
    *, actor, access_id, version: int, outcome: str, note: str = "", request=None
) -> EmergencyAccess:
    """Medical records review an ended emergency access; never the person who used it."""
    if actor is not None and not may_review_emergency_access(actor):
        raise ScopeViolation("Only medical records review emergency access.")
    access = lock_for_update(EmergencyAccess, pk=access_id, expected_version=version)
    state = state_of(access)
    if state == State.REVIEWED:
        raise ConflictError("This emergency access was already reviewed.", code="ALREADY_REVIEWED")
    if state == State.ACTIVE:
        raise ConflictError(
            "This emergency access is still open; review it once it has ended.",
            code="STILL_OPEN",
        )
    if actor is not None and access.user_id == actor.pk:
        raise ConflictError(
            "Someone else from medical records must review your own emergency access.",
            code="SAME_PERSON",
        )
    if outcome not in Outcome.values:
        raise ValidationError({"outcome": "Choose appropriate or not appropriate."})
    note = " ".join((note or "").split())
    if outcome == Outcome.NOT_APPROPRIATE and not note:
        raise ValidationError({"note": "Say what was wrong and what follows."})
    access.reviewed_at, access.reviewed_by = timezone.now(), actor
    access.outcome, access.review_note = outcome, note
    bump_version(access)
    access.save()
    _audit(
        AuditAction.EMERGENCY_ACCESS_REVIEWED,
        access.patient,
        actor=actor,
        request=request,
        reason=note,
        metadata={"emergency_access": str(access.pk), "outcome": outcome},
    )
    return access


def restricted_openings(since):
    """Openings of restricted records since then, newest first (for medical records)."""
    from apps.audit.api.views import with_names

    return with_names(
        AuditEvent.objects.filter(
            action=AuditAction.PATIENT_RECORD_VIEWED,
            resource_type="patient",
            metadata__restricted=True,
            occurred_at__gte=since,
        )
    ).order_by("-occurred_at")
