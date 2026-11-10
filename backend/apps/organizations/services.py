from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.services import AuditAction, model_changes, record_audit_event, snapshot
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError

from .logo import logo_type, validate_logo
from .models import Organization

UPDATABLE_FIELDS = (
    "legal_name",
    "display_name",
    "default_timezone",
    "leave_year_start_month",
    "letterhead_address",
    "letterhead_phone",
    "letterhead_email",
    "letterhead_website",
    "letterhead_registration",
    "letterhead_footer",
)


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


def _delete_old_logo(name: str) -> None:
    """Once the change is saved. A file left behind is harmless, so a failure only stays there."""
    if not name:
        return
    storage = Organization._meta.get_field("logo").storage
    transaction.on_commit(lambda: storage.delete(name))


@transaction.atomic
def set_logo(*, actor, organization_id, upload, request=None) -> Organization:
    """Replace the hospital's logo. A picture is whole, so there is no version to compare."""
    try:
        validate_logo(upload)
    except ValidationError as exc:
        raise ValidationError({"file": exc.messages}) from exc
    organization = Organization.objects.select_for_update().get(pk=organization_id)
    old_name = organization.logo.name
    content_type = logo_type(upload)
    organization.logo = upload
    bump_version(organization)
    organization.save()
    _delete_old_logo(old_name)
    record_audit_event(
        action=AuditAction.ORGANIZATION_LOGO_CHANGED,
        resource_type="organization",
        resource_id=organization.pk,
        actor=actor,
        request=request,
        metadata={"change": "set", "content_type": content_type, "size_bytes": upload.size},
    )
    return organization


@transaction.atomic
def remove_logo(*, actor, organization_id, request=None) -> Organization:
    organization = Organization.objects.select_for_update().get(pk=organization_id)
    old_name = organization.logo.name
    if not old_name:
        return organization
    organization.logo = ""
    bump_version(organization)
    organization.save()
    _delete_old_logo(old_name)
    record_audit_event(
        action=AuditAction.ORGANIZATION_LOGO_CHANGED,
        resource_type="organization",
        resource_id=organization.pk,
        actor=actor,
        request=request,
        metadata={"change": "removed"},
    )
    return organization
