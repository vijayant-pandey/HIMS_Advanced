"""Tamper evidence for the audit log (spec 13.4 "tamper detection"; HIMS-SEC-010, ADR-013).

How it works, in plain words:

1. Every audit event is written as before (append-only table, database trigger).
2. Shortly afterwards it is *sealed*: its fingerprint (SHA-256 over every field) becomes the next
   link of a chain. Each link also covers the previous link and is signed with a key that is
   kept outside the database (HMAC-SHA256, ``HIMS_AUDIT_CHAIN_KEYS``, newest first).
3. The integrity check walks the whole chain and recomputes every fingerprint and link.

The check finds: an event changed after it was sealed; sealed events or links deleted (a gap or
a broken link); links rebuilt without the key; the end of the chain cut off or rewritten (compared
with the previous check); events slipped in with an old time so they were never sealed.

It cannot find on its own: an event forged in the minute between being written and being
sealed, or an attacker holding both the database and the key. Each check's *chain head* is shown
to auditors so it can be kept outside HIMS; copying it to write-once storage (S3 Object Lock) is
HIMS-SEC-016, once AWS is decided.
"""

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from common.crypto import LOCAL_ENVIRONMENTS
from common.exceptions import ConflictError

from .models import AuditChainEntry, AuditEvent, AuditIntegrityCheck
from .services import AuditAction, record_audit_event

logger = logging.getLogger(__name__)

GENESIS = "0" * 64  # "previous link" of the very first link
FORMAT = "v1"  # bump if the fingerprint layout ever changes; older links keep their format
SEAL_BATCH = 1000
VERIFY_CHUNK = 2000
MAX_PROBLEMS_KEPT = 100  # every problem is counted; the first 100 are kept with details
LOCAL_KEY_ID = "local"
# PostgreSQL advisory lock numbers (fixed, used only here).
_SEAL_LOCK = 7_301_001
_CHECK_LOCK = 7_301_002

# Every column of an audit event goes into its fingerprint.
HASHED_FIELDS = (
    "id",
    "occurred_at",
    "organization_id",
    "facility_id",
    "actor_type",
    "actor_id",
    "action",
    "resource_type",
    "resource_id",
    "outcome",
    "reason",
    "request_id",
    "ip_address",
    "user_agent",
    "changes",
    "metadata",
)

PROBLEM_TEXT = {
    "event_changed": "This event was changed after it was sealed.",
    "event_missing": "This event was deleted after it was sealed.",
    "links_missing": "Links of the chain are missing (sealed events were removed).",
    "link_broken": "This link does not follow on from the one before it.",
    "link_changed": "This link was changed or rebuilt without the key.",
    "unknown_key": "This link was signed with a key that is not configured.",
    "chain_cut": "The chain is shorter than at the previous check (the newest links were removed).",
    "chain_rewritten": "The chain no longer matches the previous check (links were rebuilt).",
    "not_sealed": "This event is older than the sealing window but was never sealed "
    "(written outside the normal path, or with a back-dated time).",
}


# --- Keys ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ChainKeys:
    current_id: str
    secrets: dict[str, bytes]


@lru_cache(maxsize=4)
def _parse_keys(entries: tuple[str, ...], environment: str, secret_key: str) -> ChainKeys:
    secrets: dict[str, bytes] = {}
    order: list[str] = []
    for entry in entries:
        key_id, _, secret = entry.strip().partition(":")
        if not key_id or not secret:
            raise ImproperlyConfigured("HIMS_AUDIT_CHAIN_KEYS entries look like 'key-id:secret'.")
        secrets[key_id] = secret.encode()
        order.append(key_id)
    if environment in LOCAL_ENVIRONMENTS:
        # Developer machines and tests: a key derived from DJANGO_SECRET_KEY, kept available
        # for checking older links even after a real key is configured.
        derived = hashlib.sha256(f"hims-audit-chain:{secret_key}".encode()).digest()
        secrets.setdefault(LOCAL_KEY_ID, derived)
        if not order:
            order.append(LOCAL_KEY_ID)
    if not order:
        raise ImproperlyConfigured("HIMS_AUDIT_CHAIN_KEYS must be set in managed environments.")
    return ChainKeys(current_id=order[0], secrets=secrets)


def chain_keys() -> ChainKeys:
    return _parse_keys(
        tuple(settings.HIMS_AUDIT_CHAIN_KEYS), settings.HIMS_ENVIRONMENT, settings.SECRET_KEY
    )


# --- Fingerprints --------------------------------------------------------------------------


def _plain(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if value is None or isinstance(value, (str, int, float, bool, list, dict)):
        return value
    return str(value)  # UUIDs


def event_fingerprint(row: dict) -> str:
    """SHA-256 over every field of an event, as read back from the database."""
    payload = {name: _plain(row[name]) for name in HASHED_FIELDS}
    text = json.dumps(
        [FORMAT, payload],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        cls=DjangoJSONEncoder,
    )
    return hashlib.sha256(text.encode()).hexdigest()


def link_hash(
    secret: bytes, *, sequence: int, previous_hash: str, event_hash: str, event_id
) -> str:
    message = f"{FORMAT}|{sequence}|{previous_hash}|{event_hash}|{event_id}".encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


# --- Sealing -------------------------------------------------------------------------------


def _lookback() -> timedelta:
    return timedelta(hours=settings.HIMS_AUDIT_SEAL_LOOKBACK_HOURS)


def _last_link() -> dict | None:
    return (
        AuditChainEntry.objects.order_by("-sequence")
        .values("sequence", "entry_hash", "sealed_at", "event__occurred_at")
        .first()
    )


def sealing_window_start(last: dict | None = None) -> datetime | None:
    """Events from this time on are still picked up by sealing; None means every event."""
    last = last if last is not None else _last_link()
    if last is None:
        return None
    return last["event__occurred_at"] - _lookback()


def _pending(last: dict | None):
    pending = AuditEvent.objects.filter(chain_entry__isnull=True)
    start = sealing_window_start(last) if last else None
    return pending.filter(occurred_at__gte=start) if start else pending


def _seal_batch(batch_size: int) -> int:
    keys = chain_keys()
    secret = keys.secrets[keys.current_id]
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_SEAL_LOCK])
        last = _last_link()
        rows = list(
            _pending(last).order_by("occurred_at", "id").values(*HASHED_FIELDS)[:batch_size]
        )
        sequence = last["sequence"] if last else 0
        previous = last["entry_hash"] if last else GENESIS
        now = timezone.now()
        links = []
        for row in rows:
            sequence += 1
            event_hash = event_fingerprint(row)
            entry_hash = link_hash(
                secret,
                sequence=sequence,
                previous_hash=previous,
                event_hash=event_hash,
                event_id=row["id"],
            )
            links.append(
                AuditChainEntry(
                    sequence=sequence,
                    event_id=row["id"],
                    event_hash=event_hash,
                    previous_hash=previous,
                    entry_hash=entry_hash,
                    key_id=keys.current_id,
                    sealed_at=now,
                )
            )
            previous = entry_hash
        AuditChainEntry.objects.bulk_create(links)
    return len(links)


def seal_pending_events(*, batch_size: int = SEAL_BATCH) -> int:
    """Add every committed, not yet sealed event to the chain. Safe to run at any time and
    from several workers at once (one seals while the others wait). Returns how many."""
    total = 0
    while True:
        sealed = _seal_batch(batch_size)
        total += sealed
        if sealed < batch_size:
            return total


# --- Checking ------------------------------------------------------------------------------


@dataclass
class _Findings:
    problems: list
    count: int = 0

    def add(self, kind: str, **details) -> None:
        self.count += 1
        if len(self.problems) < MAX_PROBLEMS_KEPT:
            self.problems.append({"kind": kind, "text": PROBLEM_TEXT[kind], **details})


def _event_details(row: dict | None) -> dict:
    if row is None:
        return {}
    return {"action": row["action"], "occurred_at": _plain(row["occurred_at"])}


def _walk_chain(keys: ChainKeys, findings: _Findings) -> tuple[int, int, str]:
    """Recompute every link up to the current end. Returns (checked, last sequence, head)."""
    end = AuditChainEntry.objects.order_by("-sequence").values_list("sequence", flat=True).first()
    if end is None:
        return 0, 0, ""
    expected, previous, checked, after = 1, GENESIS, 0, 0
    while True:
        chunk = list(
            AuditChainEntry.objects.filter(sequence__gt=after, sequence__lte=end)
            .order_by("sequence")
            .values("sequence", "event_id", "event_hash", "previous_hash", "entry_hash", "key_id")[
                :VERIFY_CHUNK
            ]
        )
        if not chunk:
            break
        events = {
            row["id"]: row
            for row in AuditEvent.objects.filter(
                pk__in=[link["event_id"] for link in chunk]
            ).values(*HASHED_FIELDS)
        }
        for link in chunk:
            sequence = link["sequence"]
            event = events.get(link["event_id"])
            where = {
                "sequence": sequence,
                "event_id": str(link["event_id"]),
                **_event_details(event),
            }
            if sequence != expected:
                findings.add("links_missing", sequence=expected, last_missing=sequence - 1)
            elif link["previous_hash"] != previous:
                findings.add("link_broken", **where)
            secret = keys.secrets.get(link["key_id"])
            if secret is None:
                findings.add("unknown_key", key_id=link["key_id"], **where)
            else:
                expected_hash = link_hash(
                    secret,
                    sequence=sequence,
                    previous_hash=link["previous_hash"],
                    event_hash=link["event_hash"],
                    event_id=link["event_id"],
                )
                if not hmac.compare_digest(expected_hash, link["entry_hash"]):
                    findings.add("link_changed", **where)
            if event is None:
                findings.add("event_missing", **where)
            elif event_fingerprint(event) != link["event_hash"]:
                findings.add("event_changed", **where)
            previous, expected, checked = link["entry_hash"], sequence + 1, checked + 1
        after = chunk[-1]["sequence"]
    return checked, end, previous


def _compare_with_previous_check(last_sequence: int, findings: _Findings) -> None:
    earlier = (
        AuditIntegrityCheck.objects.filter(last_sequence__gt=0).order_by("-finished_at").first()
    )
    if earlier is None:
        return
    if earlier.last_sequence > last_sequence:
        findings.add(
            "chain_cut", previous_last_sequence=earlier.last_sequence, last_sequence=last_sequence
        )
        return
    stored = (
        AuditChainEntry.objects.filter(sequence=earlier.last_sequence)
        .values_list("entry_hash", flat=True)
        .first()
    )
    if stored != earlier.chain_head:
        findings.add("chain_rewritten", sequence=earlier.last_sequence)


def _never_sealed(findings: _Findings) -> int:
    start = sealing_window_start()
    if start is None:
        return 0
    late = AuditEvent.objects.filter(chain_entry__isnull=True, occurred_at__lt=start)
    count = late.count()
    for row in late.order_by("occurred_at").values(*HASHED_FIELDS)[:MAX_PROBLEMS_KEPT]:
        findings.add("not_sealed", event_id=str(row["id"]), **_event_details(row))
    return count


def run_integrity_check(*, trigger: str, actor=None, request=None) -> AuditIntegrityCheck:
    """Seal anything pending, then check the whole chain. The result is stored (never
    changed), written to the audit log, and auditors are emailed if problems are found."""
    started = timezone.now()
    sealed = seal_pending_events()
    keys = chain_keys()
    findings = _Findings(problems=[])
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [_CHECK_LOCK])
            if not cursor.fetchone()[0]:
                raise ConflictError(
                    "An integrity check is already running. Try again in a minute.",
                    code="CHECK_RUNNING",
                )
        checked, last_sequence, head = _walk_chain(keys, findings)
        _compare_with_previous_check(last_sequence, findings)
        unsealed = _never_sealed(findings)
        passed = findings.count == 0
        check = AuditIntegrityCheck.objects.create(
            started_at=started,
            trigger=trigger,
            requested_by_id=actor.pk if actor is not None else None,
            outcome=(
                AuditIntegrityCheck.Outcome.PASSED if passed else AuditIntegrityCheck.Outcome.FAILED
            ),
            events_sealed=sealed,
            entries_checked=checked,
            last_sequence=last_sequence,
            chain_head=head,
            problem_count=findings.count,
            problems=findings.problems,
            unsealed_overdue=unsealed,
        )
        record_audit_event(
            action=AuditAction.AUDIT_INTEGRITY_CHECKED,
            resource_type="audit_integrity_check",
            resource_id=check.pk,
            actor=actor,
            request=request,
            outcome=AuditEvent.Outcome.SUCCESS if passed else AuditEvent.Outcome.FAILURE,
            metadata={
                "trigger": trigger,
                "events_sealed": sealed,
                "links_checked": checked,
                "last_sequence": last_sequence,
                "chain_head": head,
                "problems": findings.count,
                "never_sealed": unsealed,
            },
        )
    if not passed:
        logger.error(
            "audit_integrity_check_failed",
            extra={"check_id": str(check.pk), "problems": findings.count},
        )
        _alert_auditors(check)
    return check


# --- Alerts and status ---------------------------------------------------------------------


def auditor_emails() -> list[str]:
    """Active people holding ``audit.view`` (auditors / compliance)."""
    from apps.access_control.catalog import P
    from apps.access_control.models import RoleAssignment

    now = timezone.now()
    emails = (
        RoleAssignment.objects.filter(
            Q(valid_until__isnull=True) | Q(valid_until__gt=now),
            revoked_at__isnull=True,
            valid_from__lte=now,
            user__is_active=True,
            role__role_permissions__permission__codename=P.AUDIT_VIEW,
            role__role_permissions__permission__is_active=True,
        )
        .values_list("user__email", flat=True)
        .distinct()
    )
    return sorted(set(emails))


def _alert_auditors(check: AuditIntegrityCheck) -> None:
    recipients = auditor_emails()
    link = f"{settings.HIMS_APP_BASE_URL.rstrip('/')}/audit/integrity/{check.pk}"
    body = (
        "The audit log integrity check found "
        f"{check.problem_count} problem(s) on {check.finished_at:%Y-%m-%d %H:%M} UTC.\n\n"
        "This can mean that someone changed or removed audit records directly in the database.\n"
        "Treat it as a possible security incident: do not change anything, and follow the\n"
        "incident procedure.\n\n"
        f"See the details (sign-in needed): {link}\n"
    )
    if recipients:
        send_mail(
            subject="HIMS: audit log integrity check found problems",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
        )
    record_audit_event(
        action=AuditAction.AUDIT_INTEGRITY_ALERT_SENT,
        resource_type="audit_integrity_check",
        resource_id=check.pk,
        outcome=AuditEvent.Outcome.SUCCESS if recipients else AuditEvent.Outcome.FAILURE,
        metadata={"recipients": len(recipients)},
        reason="" if recipients else "Nobody holds audit.view, so nobody could be emailed.",
    )


def integrity_status() -> dict:
    last = _last_link()
    start = sealing_window_start(last)
    waiting = AuditEvent.objects.filter(chain_entry__isnull=True)
    if start is not None:
        waiting = waiting.filter(occurred_at__gte=start)
    return {
        "sealed_events": last["sequence"] if last else 0,
        "last_sealed_at": last["sealed_at"] if last else None,
        "chain_head": last["entry_hash"] if last else "",
        "waiting_to_be_sealed": waiting.count(),
        "key_id": chain_keys().current_id,
        "last_check": AuditIntegrityCheck.objects.order_by("-finished_at").first(),
    }
