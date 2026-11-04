"""Compliance registers: rules for requirements and risks (spec 13, 23, 26.7; HIMS-COMP)."""

from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditAction, record_audit_event
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError

from . import catalog
from .models import ComplianceRequirement, RiskEntry

Status = ComplianceRequirement.Status


def sync_catalog() -> None:
    """Add new catalog rows and refresh wording. Never touches the hospital's status, owner or
    evidence. Rows removed from the catalog are switched off, not deleted."""
    codes = []
    for (
        code,
        jurisdiction,
        regulation,
        citation,
        title,
        summary,
        support,
        start,
    ) in catalog.REQUIREMENTS:
        codes.append(code)
        ComplianceRequirement.objects.update_or_create(
            code=code,
            defaults={
                "jurisdiction": jurisdiction,
                "regulation": regulation,
                "citation": citation,
                "title": title,
                "summary": summary,
                "hims_support": support,
                "is_active": True,
            },
            create_defaults={
                "jurisdiction": jurisdiction,
                "regulation": regulation,
                "citation": citation,
                "title": title,
                "summary": summary,
                "hims_support": support,
                "status": start,
            },
        )
    ComplianceRequirement.objects.exclude(code__in=codes).update(is_active=False)
    for code, title, description, category, likelihood, impact, mitigation in catalog.RISKS:
        RiskEntry.objects.get_or_create(
            code=code,
            defaults={
                "title": title,
                "description": description,
                "category": category,
                "likelihood": likelihood,
                "impact": impact,
                "mitigation": mitigation,
                "status": RiskEntry.Status.TREATING,
            },
        )


def next_risk_code() -> str:
    numbers = [
        int(code.split("-")[1])
        for code in RiskEntry.objects.values_list("code", flat=True)
        if code.startswith("R-") and code.split("-")[1].isdigit()
    ]
    return f"R-{max(numbers, default=0) + 1:03d}"


@transaction.atomic
def update_requirement(*, actor, requirement_id, version, request=None, **changes):
    item = lock_for_update(ComplianceRequirement, pk=requirement_id, expected_version=version)
    before = {name: str(getattr(item, name)) for name in changes}
    for name, value in changes.items():
        setattr(item, name, value)
    if item.status == Status.VERIFIED and not item.evidence.strip():
        raise ConflictError(
            "Say where the proof is before marking this verified.", code="NO_EVIDENCE"
        )
    item.reviewed_by = actor
    item.reviewed_at = timezone.now()
    bump_version(item)
    item.save()
    record_audit_event(
        action=AuditAction.COMPLIANCE_REQUIREMENT_UPDATED,
        resource_type="compliance_requirement",
        resource_id=item.pk,
        actor=actor,
        request=request,
        changes={"before": before, "after": {name: str(getattr(item, name)) for name in changes}},
        metadata={"code": item.code},
    )
    return item


def _check_acceptance(risk: RiskEntry) -> None:
    accepted = (
        risk.status == RiskEntry.Status.ACCEPTED or risk.treatment == RiskEntry.Treatment.ACCEPT
    )
    if accepted and not risk.acceptance_reason.strip():
        raise ConflictError("Give the reason for accepting this risk.", code="REASON_REQUIRED")


@transaction.atomic
def create_risk(*, actor, request=None, **fields) -> RiskEntry:
    risk = RiskEntry(code=next_risk_code(), updated_by=actor, **fields)
    _check_acceptance(risk)
    risk.save()
    record_audit_event(
        action=AuditAction.COMPLIANCE_RISK_CREATED,
        resource_type="compliance_risk",
        resource_id=risk.pk,
        actor=actor,
        request=request,
        metadata={"code": risk.code, "score": risk.score},
    )
    return risk


@transaction.atomic
def update_risk(*, actor, risk_id, version, request=None, **changes) -> RiskEntry:
    risk = lock_for_update(RiskEntry, pk=risk_id, expected_version=version)
    before = {name: str(getattr(risk, name)) for name in changes}
    for name, value in changes.items():
        setattr(risk, name, value)
    _check_acceptance(risk)
    risk.updated_by = actor
    bump_version(risk)
    risk.save()
    record_audit_event(
        action=AuditAction.COMPLIANCE_RISK_UPDATED,
        resource_type="compliance_risk",
        resource_id=risk.pk,
        actor=actor,
        request=request,
        changes={"before": before, "after": {name: str(getattr(risk, name)) for name in changes}},
        metadata={"code": risk.code, "score": risk.score},
    )
    return risk
