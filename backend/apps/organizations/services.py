from django.conf import settings
from django.db import transaction

from apps.audit.services import AuditAction, model_changes, record_audit_event, snapshot
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError

from .models import Organization

UPDATABLE_FIELDS = ("legal_name", "display_name", "default_timezone")


@transaction.atomic
def provision_organization(
    *,
    legal_name: str,
    display_name: str,
    country: str,
    default_timezone: str,
    default_currency: str,
) -> Organization:
    """Create this deployment's organization. Called by provisioning automation only."""
    if Organization.objects.exists():
        raise ConflictError("This deployment already has its organization.")
    organization = Organization(
        deployment_id=settings.HIMS_DEPLOYMENT_ID,
        legal_name=legal_name,
        display_name=display_name,
        country=country,
        default_timezone=default_timezone,
        default_currency=default_currency,
    )
    organization.full_clean()
    organization.save()
    record_audit_event(
        action=AuditAction.ORGANIZATION_PROVISIONED,
        resource_type="organization",
        resource_id=organization.pk,
        organization_id=organization.pk,
        changes={"after": snapshot(organization)},
    )
    return organization


@transaction.atomic
def update_organization(*, actor, organization_id, version: int, request=None, **changes):
    organization = lock_for_update(Organization, pk=organization_id, expected_version=version)
    before = snapshot(organization, UPDATABLE_FIELDS)
    for field, value in changes.items():
        if field not in UPDATABLE_FIELDS:
            raise ValueError(f"{field} is not updatable")
        setattr(organization, field, value)
    organization.full_clean()
    bump_version(organization)
    organization.save()
    record_audit_event(
        action=AuditAction.ORGANIZATION_UPDATED,
        resource_type="organization",
        resource_id=organization.pk,
        actor=actor,
        request=request,
        changes=model_changes(before, snapshot(organization, UPDATABLE_FIELDS)),
    )
    return organization
