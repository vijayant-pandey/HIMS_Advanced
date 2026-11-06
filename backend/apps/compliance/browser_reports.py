"""What browsers blocked under the security headers (spec 13; HIMS-SEC-012).

Browsers send these reports without signing in, so anything here may be made up. Only the kind of
rule, the blocked site and the page address are kept: never query strings or code samples, which
could carry patient details. Reports are added up per day and capped, so flooding the address
cannot fill the database.
"""

import logging
import re
from urllib.parse import urlsplit

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.audit.services import AuditAction, record_audit_event
from apps.organizations.dates import hospital_today
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError

from .models import BrowserSecurityReport

logger = logging.getLogger(__name__)

MAX_REPORT_BYTES = 16 * 1024
MAX_ROWS_PER_DAY = 500
_DIRECTIVE = re.compile(r"^[a-z-]{1,64}$")
_KEYWORD = re.compile(r"^[a-z-]{1,32}$")  # "inline", "eval", "data", "blob" ...
_ID_IN_PATH = re.compile(
    r"(?<=/)(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|\d+)(?=/|$)"
)


def _blocked_site(value: str) -> str:
    value = (value or "").strip()
    if _KEYWORD.match(value):
        return value
    parts = urlsplit(value)
    if parts.scheme in ("http", "https", "ws", "wss") and parts.hostname:
        port = f":{parts.port}" if parts.port else ""
        return f"{parts.scheme}://{parts.hostname}{port}"[:200]
    return parts.scheme[:32] if parts.scheme else "other"


def _page_path(value: str) -> str:
    return _ID_IN_PATH.sub("{id}", urlsplit(value or "").path)[:200]


def record_report(payload: object) -> bool:
    """Add one browser report to today's totals. Returns False if it was ignored."""
    report = payload.get("csp-report") if isinstance(payload, dict) else None
    if not isinstance(report, dict):
        return False
    try:
        directive = str(report.get("effective-directive") or report.get("violated-directive") or "")
        directive = directive.split(" ")[0]
        blocked = _blocked_site(str(report.get("blocked-uri") or ""))
        page_path = _page_path(str(report.get("document-uri") or ""))
    except ValueError:  # not a usable address
        return False
    if not _DIRECTIVE.match(directive):
        return False
    today = hospital_today()
    key = {"day": today, "directive": directive, "blocked": blocked, "page_path": page_path}
    if BrowserSecurityReport.objects.filter(**key).update(
        occurrences=F("occurrences") + 1, last_seen_at=timezone.now()
    ):
        return True
    if BrowserSecurityReport.objects.filter(day=today).count() >= MAX_ROWS_PER_DAY:
        logger.warning("browser_report_cap_reached", extra={"day": str(today)})
        return False
    _, created = BrowserSecurityReport.objects.get_or_create(**key)
    if not created:  # another report for the same thing arrived in between
        BrowserSecurityReport.objects.filter(**key).update(occurrences=F("occurrences") + 1)
    return True


@transaction.atomic
def review_report(*, actor, report_id, version, note="", request=None) -> BrowserSecurityReport:
    report = lock_for_update(BrowserSecurityReport, pk=report_id, expected_version=version)
    if report.reviewed_at:
        raise ConflictError("This has already been reviewed.", code="already_reviewed")
    report.reviewed_by = actor
    report.reviewed_at = timezone.now()
    report.review_note = note
    bump_version(report)
    report.save()
    record_audit_event(
        action=AuditAction.COMPLIANCE_BROWSER_REPORT_REVIEWED,
        resource_type="browser_security_report",
        resource_id=report.pk,
        actor=actor,
        request=request,
        changes={"after": {"reviewed": True, "note": note}},
        metadata={"directive": report.directive, "blocked": report.blocked},
    )
    return report
