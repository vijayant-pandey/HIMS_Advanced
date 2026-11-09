"""Who the admin console refused, and where it may be used from (spec 13.1, 13.4; HIMS-SEC-015).

The check itself is common/admin/allowed_addresses.py. Refusals are added up per day and
address and capped, so knocking on the console from many addresses cannot fill the database.
The first refusal of an address each day is audited, and so is the first one that carries a
signed-in session (a session used from an address its owner never uses may have been stolen).
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction, record_audit_event
from apps.organizations.dates import hospital_today
from common.client_ip import client_ip, console_allows
from common.concurrency import bump_version, lock_for_update
from common.environment import LOCAL_ENVIRONMENTS
from common.exceptions import ConflictError

from .browser_reports import MAX_ROWS_PER_DAY, _page_path
from .models import ConsoleAccessBlock

logger = logging.getLogger(__name__)


def _signed_in_user(request):
    """The person whose console session came with the request, if any. The check runs before
    Django attaches request.user, so the session is read here."""
    user = get_user(request) if hasattr(request, "session") else None
    return user if user is not None and user.is_authenticated else None


def _audit(request, block, user, *, signed_in: bool) -> None:
    record_audit_event(
        action=AuditAction.AUTH_CONSOLE_ADDRESS_REFUSED,
        resource_type="console_access_block",
        resource_id=block.pk,
        actor=user,
        request=request,
        outcome=AuditEvent.Outcome.DENIED,
        metadata={"page": block.last_path, "signed_in": signed_in},
    )


def record_refusal(request, address: str | None) -> ConsoleAccessBlock | None:
    """Count one refused console request. Returns None when it was not counted."""
    if not address:
        return None
    user = _signed_in_user(request)
    today = hospital_today()
    page = _page_path(request.path)
    key = {"day": today, "ip_address": address}
    with transaction.atomic():
        block = ConsoleAccessBlock.objects.select_for_update().filter(**key).first()
        if block is None:
            if ConsoleAccessBlock.objects.filter(day=today).count() >= MAX_ROWS_PER_DAY:
                logger.warning("console_refusal_cap_reached", extra={"day": str(today)})
                return None
            block, created = ConsoleAccessBlock.objects.get_or_create(
                **key, defaults={"last_path": page, "signed_in_user": user}
            )
            if created:
                _audit(request, block, user, signed_in=user is not None)
                return block
            block = ConsoleAccessBlock.objects.select_for_update().get(pk=block.pk)
        newly_signed_in = user is not None and block.signed_in_user_id != user.pk
        block.attempts += 1
        block.last_seen_at = timezone.now()
        block.last_path = page
        if user is not None:
            block.signed_in_user = user
        block.save(update_fields=["attempts", "last_seen_at", "last_path", "signed_in_user"])
        if newly_signed_in:
            _audit(request, block, user, signed_in=True)
    return block


@transaction.atomic
def review_block(*, actor, block_id, version, note="", request=None) -> ConsoleAccessBlock:
    block = lock_for_update(ConsoleAccessBlock, pk=block_id, expected_version=version)
    if block.reviewed_at:
        raise ConflictError("This has already been reviewed.", code="already_reviewed")
    block.reviewed_by = actor
    block.reviewed_at = timezone.now()
    block.review_note = note
    bump_version(block)
    block.save()
    record_audit_event(
        action=AuditAction.COMPLIANCE_CONSOLE_BLOCK_REVIEWED,
        resource_type="console_access_block",
        resource_id=block.pk,
        actor=actor,
        request=request,
        changes={"after": {"reviewed": True, "note": note}},
        metadata={"day": str(block.day), "attempts": block.attempts},
    )
    return block


def console_status(request) -> dict:
    """Where the console may be used from, and whether the person asking is allowed."""
    address = client_ip(request)
    return {
        "enabled": settings.HIMS_ENABLE_ADMIN,
        "allowed_networks": list(settings.HIMS_ADMIN_ALLOWED_NETWORKS),
        "your_address": address,
        "you_are_allowed": console_allows(address),
        "developer_pc": settings.HIMS_ENVIRONMENT in LOCAL_ENVIRONMENTS,
        "refusals_to_review": ConsoleAccessBlock.objects.filter(reviewed_at__isnull=True).count(),
    }
