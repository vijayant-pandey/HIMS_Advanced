"""The patient chart's header and overview, and the record's history (HIMS-PAT-005; spec 15.3).

The header is what every screen showing a patient keeps in view (P0 part 01 section 7): name,
MRN, age and sex, the allergy status and the flags that change how staff act (unknown patient,
merged record, a child without a guardian). The same alerts show in the app and in the admin
console, so they are worked out here once.

Allergies are recorded with HIMS-CLIN-003. Until then every patient's allergies are "not asked
yet", which is the truth and what the header must say when nothing is recorded (D19); restricted
and deceased flags come with HIMS-PAT-006 and HIMS-PAT-007.

The record's history lists who opened the record and who changed what, and when, from the audit
log (P0 part 04: medical records see who opened a chart; auditors search the whole audit log).
It names the fields that changed, never their old or new values: those stay in the audit log.
"""

from dataclasses import dataclass

from django.db import models

from apps.audit.api.views import with_names
from apps.audit.models import AuditEvent
from apps.organizations.dates import hospital_today

from . import demographics
from .models import Patient, PatientConsent
from .services import ADULT_AGE, GUARDIAN_RELATIONS


class AllergyStatus(models.TextChoices):
    """What the header says about allergies. HIMS-CLIN-003 adds "no known allergies" and the
    recorded allergies themselves (shown in red)."""

    NOT_ASKED = "not_asked", "Allergies not asked yet"


class Severity(models.TextChoices):
    WARNING = "warning", "Warning"
    INFO = "info", "Information"


@dataclass(frozen=True)
class Alert:
    code: str
    severity: str
    message: str


def needs_guardian(patient: Patient) -> bool:
    """Under 18 with no current parent or guardian recorded (reads prefetched relationships)."""
    if patient.is_unknown:
        return False
    if demographics.years_between(patient.date_of_birth, hospital_today()) >= ADULT_AGE:
        return False
    return not any(
        r.is_active and (r.is_legal_guardian or r.relation in GUARDIAN_RELATIONS)
        for r in patient.relationships.all()
    )


def _has_privacy_notice(patient: Patient) -> bool:
    latest = next(
        (c for c in patient.consents.all() if c.kind == PatientConsent.Kind.PRIVACY_NOTICE), None
    )
    return latest is not None and latest.status == PatientConsent.Status.GIVEN


def alerts(patient: Patient) -> list[Alert]:
    """What staff must notice on opening the record, most important first. Reads the prefetched
    contacts, relationships and consents (consents newest first)."""
    found = []
    if patient.status == Patient.Status.MERGED:
        target = patient.merged_into.mrn if patient.merged_into else ""
        found.append(
            Alert(
                "merged",
                Severity.WARNING,
                f"This record was merged into {target}. Open that record for care.",
            )
        )
    if patient.is_unknown:
        found.append(
            Alert(
                "unknown",
                Severity.WARNING,
                "Unknown patient: correct the name, date of birth and contacts when known.",
            )
        )
    if needs_guardian(patient):
        found.append(
            Alert(
                "needs_guardian",
                Severity.WARNING,
                "Under 18 with no parent or guardian recorded. Add one under People.",
            )
        )
    if not _has_privacy_notice(patient):
        found.append(
            Alert(
                "no_privacy_notice",
                Severity.INFO,
                "The privacy notice is not recorded as given. Record it under Consent.",
            )
        )
    if not patient.has_no_phone and not any(c.is_active for c in patient.contacts.all()):
        found.append(
            Alert("no_contact", Severity.INFO, "No phone, email or address recorded. Add one.")
        )
    return found


FIELD_NAMES = {"is_primary": "main contact", "blood_group_reported": "blood group (reported)"}


def history(patient: Patient):
    """The record's events, newest first: opened, registered, corrected, contacts, people, ID
    numbers, consents (the audit index on resource and time serves it)."""
    events = AuditEvent.objects.filter(resource_type="patient", resource_id=str(patient.pk))
    return with_names(events).order_by("-occurred_at")


def changed_fields(event: AuditEvent) -> list[str]:
    """For a correction: the names of the fields that changed, never their values."""
    if not event.action.endswith(".updated"):
        return []
    after = (event.changes or {}).get("after") or {}
    names = []
    for name, value in after.items():
        if name == "is_active":
            names.append("ended" if value is False else "active again")
        else:
            names.append(FIELD_NAMES.get(name, name.replace("_", " ")))
    return names
