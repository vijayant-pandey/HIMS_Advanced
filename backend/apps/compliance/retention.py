"""Retention purge with legal hold (spec 4.25 "retention, legal holds, export controls and
deletion restrictions", 28.1 #5, 28.2; HIMS-COMP-006). Runbook: docs/workflows/retention-purge.md.

Rules:
* Only the housekeeping records listed in ``CATEGORIES`` can be purged. The audit log, staff
  records, compliance registers and (from Phase 2) clinical and financial records are never
  deleted by this job: spec 28.2 forbids erasing signed facts, and the audit chain needs an
  archive marker first (HIMS-COMP-007).
* Nothing is deleted until the hospital sets a period for a kind (decision log #7). Each kind has
  a minimum, so a typing mistake cannot empty it.
* A shorter period (or the first one) waits ``SHORTER_PERIOD_WAIT`` before it applies, so a
  mistake can be undone before anything goes. A longer one, or "keep for ever", applies at once.
* An active legal hold always wins: on a whole kind, or on the records about one person.
* Each run deletes in small batches, at most ``RUN_LIMIT`` rows per kind (the rest go the next
  day), and is recorded with its counts (append-only) and in the audit log.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import connection, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.audit.services import AuditAction, record_audit_event
from apps.identity.models import Invitation, PasswordReset, User, UserSession
from apps.notifications.models import Notification
from common.concurrency import bump_version
from common.exceptions import ConflictError, StaleResourceError

from .models import (
    BrowserSecurityReport,
    ConsoleAccessBlock,
    LegalHold,
    RetentionPurgeRun,
    RetentionRule,
)

logger = logging.getLogger(__name__)

SHORTER_PERIOD_WAIT = timedelta(days=7)
MAX_DAYS = 36500  # 100 years
DELETE_BATCH = 2000
RUN_LIMIT = 50000
_PURGE_LOCK = 7_406_006  # PostgreSQL advisory lock number, used only here


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    table: str
    what: str  # which rows go, in plain words
    minimum_days: int
    rows: Callable[[datetime, datetime], QuerySet]  # (cut-off, now) -> rows that may go
    about: Callable[[set], Q] | None  # rows about these people (for holds on one person)


def _closed(now) -> Q:
    return Q(used_at__isnull=False) | Q(revoked_at__isnull=False) | Q(expires_at__lt=now)


def _messages_about(user_ids: set) -> Q:
    emails = User.objects.filter(pk__in=user_ids).values_list("email", flat=True)
    about = Q(requested_by_id__in=user_ids)
    for email in emails:
        about |= Q(recipients__contains=[email])
    return about


CATEGORIES: dict[str, Category] = {
    category.key: category
    for category in (
        Category(
            key="sign_ins",
            label="Sign-in register",
            table="user_sessions",
            what="Sign-ins that ended before the cut-off. Open sessions are never touched.",
            minimum_days=365,
            rows=lambda cutoff, now: UserSession.objects.filter(ended_at__lt=cutoff),
            about=lambda ids: Q(user_id__in=ids),
        ),
        Category(
            key="messages",
            label="Message log (emails and SMS)",
            table="notifications",
            what="Messages sent, given up or not sent, created before the cut-off. Messages "
            "still waiting or being retried are never touched.",
            minimum_days=90,
            rows=lambda cutoff, now: Notification.objects.filter(
                created_at__lt=cutoff,
                status__in=(
                    Notification.Status.SENT,
                    Notification.Status.GAVE_UP,
                    Notification.Status.SKIPPED,
                ),
            ),
            about=_messages_about,
        ),
        Category(
            key="invitations",
            label="Account invitations",
            table="user_invitations",
            what="Invitations accepted, revoked or expired, sent before the cut-off.",
            minimum_days=30,
            rows=lambda cutoff, now: Invitation.objects.filter(created_at__lt=cutoff).filter(
                Q(accepted_at__isnull=False) | Q(revoked_at__isnull=False) | Q(expires_at__lt=now)
            ),
            about=lambda ids: Q(user_id__in=ids),
        ),
        Category(
            key="password_resets",
            label="Password-reset requests",
            table="user_password_resets",
            what="Requests used, revoked or expired, made before the cut-off.",
            minimum_days=30,
            rows=lambda cutoff, now: PasswordReset.objects.filter(created_at__lt=cutoff).filter(
                _closed(now)
            ),
            about=lambda ids: Q(user_id__in=ids),
        ),
        Category(
            key="browser_reports",
            label="Browser block reports",
            table="browser_security_reports",
            what="Days before the cut-off. They name no person.",
            minimum_days=30,
            rows=lambda cutoff, now: BrowserSecurityReport.objects.filter(day__lt=cutoff.date()),
            about=None,
        ),
        Category(
            key="console_refusals",
            label="Refused console addresses",
            table="console_access_blocks",
            what="Days before the cut-off that someone has reviewed. Unreviewed ones are kept.",
            minimum_days=365,
            rows=lambda cutoff, now: ConsoleAccessBlock.objects.filter(
                day__lt=cutoff.date(), reviewed_at__isnull=False
            ),
            about=lambda ids: Q(signed_in_user_id__in=ids),
        ),
    )
}

CATEGORY_CHOICES = [(key, category.label) for key, category in CATEGORIES.items()]


def _category(key: str) -> Category:
    if key not in CATEGORIES:
        raise ConflictError("No such kind of record.", code="UNKNOWN_RETENTION_CATEGORY")
    return CATEGORIES[key]


def sync_rules() -> None:
    """One rule per kind, kept for ever until the hospital sets a period."""
    for key in CATEGORIES:
        RetentionRule.objects.get_or_create(category=key)


def _rule(key: str) -> RetentionRule:
    rule, _ = RetentionRule.objects.get_or_create(category=key)
    return rule


# --- Periods ------------------------------------------------------------------------------------


@transaction.atomic
def set_period(*, actor, category, keep_days, version, request=None) -> RetentionRule:
    """Set how long a kind is kept. ``None`` = for ever. The same period as now cancels a
    shorter one that is waiting."""
    kind = _category(category)
    _rule(category)
    rule = RetentionRule.objects.select_for_update().get(category=category)
    if rule.version != version:
        raise StaleResourceError(
            "This record changed since you loaded it. Reload and re-apply your changes."
        )
    if keep_days is not None and not kind.minimum_days <= keep_days <= MAX_DAYS:
        raise ConflictError(
            f"{kind.label}: keep at least {kind.minimum_days} days (and at most {MAX_DAYS}).",
            code="RETENTION_OUT_OF_RANGE",
        )
    before = {"keep_days": rule.keep_days, "pending_keep_days": rule.pending_keep_days}
    now = timezone.now()
    if keep_days == rule.keep_days:
        if rule.pending_from is None:
            raise ConflictError("That is the period already set.", code="NO_CHANGE")
        rule.pending_keep_days = rule.pending_from = None  # cancel the waiting shorter period
    elif keep_days is None or (rule.keep_days is not None and keep_days > rule.keep_days):
        rule.keep_days = keep_days  # keeping longer is safe: applies at once
        rule.pending_keep_days = rule.pending_from = None
    else:
        rule.pending_keep_days = keep_days  # deleting sooner waits, so a mistake can be undone
        rule.pending_from = now + SHORTER_PERIOD_WAIT
    rule.updated_by = actor
    bump_version(rule)
    rule.save()
    record_audit_event(
        action=AuditAction.RETENTION_PERIOD_CHANGED,
        resource_type="retention_rule",
        resource_id=rule.pk,
        actor=actor,
        request=request,
        changes={
            "before": before,
            "after": {"keep_days": rule.keep_days, "pending_keep_days": rule.pending_keep_days},
        },
        metadata={
            "category": category,
            "applies_from": rule.pending_from.isoformat() if rule.pending_from else None,
        },
    )
    return rule


def apply_due_periods(now=None) -> list[str]:
    """Shorter periods whose waiting time is over take effect (run before each purge)."""
    now = now or timezone.now()
    applied = []
    with transaction.atomic():
        for rule in RetentionRule.objects.select_for_update().filter(pending_from__lte=now):
            before = rule.keep_days
            rule.keep_days, rule.pending_keep_days, rule.pending_from = (
                rule.pending_keep_days,
                None,
                None,
            )
            bump_version(rule)
            rule.save()
            record_audit_event(
                action=AuditAction.RETENTION_PERIOD_APPLIED,
                resource_type="retention_rule",
                resource_id=rule.pk,
                changes={"before": {"keep_days": before}, "after": {"keep_days": rule.keep_days}},
                metadata={"category": rule.category},
            )
            applied.append(rule.category)
    return applied


# --- Legal holds --------------------------------------------------------------------------------


@transaction.atomic
def place_hold(
    *, actor, reference, reason, categories=(), subject_user=None, request=None
) -> LegalHold:
    unknown = [key for key in categories if key not in CATEGORIES]
    if unknown:
        raise ConflictError("No such kind of record.", code="UNKNOWN_RETENTION_CATEGORY")
    if not reference.strip() or not reason.strip():
        raise ConflictError("Give the reference and the reason.", code="REASON_REQUIRED")
    hold = LegalHold.objects.create(
        reference=reference.strip(),
        reason=reason.strip(),
        categories=sorted(set(categories)),
        subject_user=subject_user,
        placed_by=actor,
    )
    record_audit_event(
        action=AuditAction.LEGAL_HOLD_PLACED,
        resource_type="legal_hold",
        resource_id=hold.pk,
        actor=actor,
        request=request,
        metadata={
            "reference": hold.reference,
            "categories": hold.categories or "all",
            "subject_user_id": str(subject_user.pk) if subject_user else None,
        },
        reason=hold.reason,
    )
    return hold


@transaction.atomic
def release_hold(*, actor, hold_id, version, reason, request=None) -> LegalHold:
    hold = LegalHold.objects.select_for_update().get(pk=hold_id)
    if hold.version != version:
        raise StaleResourceError(
            "This record changed since you loaded it. Reload and re-apply your changes."
        )
    if hold.released_at is not None:
        raise ConflictError("This hold was already released.", code="HOLD_RELEASED")
    if not reason.strip():
        raise ConflictError("Say why the hold can end.", code="REASON_REQUIRED")
    hold.released_by = actor
    hold.released_at = timezone.now()
    hold.release_reason = reason.strip()
    bump_version(hold)
    hold.save()
    record_audit_event(
        action=AuditAction.LEGAL_HOLD_RELEASED,
        resource_type="legal_hold",
        resource_id=hold.pk,
        actor=actor,
        request=request,
        metadata={"reference": hold.reference},
        reason=hold.release_reason,
    )
    return hold


def _holds_on(key: str, holds: list[LegalHold]) -> tuple[bool, set]:
    """(the whole kind is held, people whose records of this kind are held)."""
    whole, people = False, set()
    for hold in holds:
        if hold.categories and key not in hold.categories:
            continue
        if hold.subject_user_id is None:
            whole = True
        else:
            people.add(hold.subject_user_id)
    return whole, people


def _active_holds() -> list[LegalHold]:
    return list(LegalHold.objects.filter(released_at__isnull=True))


# --- Preview and purge --------------------------------------------------------------------------


def _plan(kind: Category, rule: RetentionRule, holds, now) -> dict:
    """What a purge of this kind would do now: the rows to delete, and why others stay."""
    plan = {
        "keep_days": rule.keep_days,
        "older_than": None,
        "skipped": "",
        "rows": None,
        "held": 0,
    }
    if rule.keep_days is None:
        plan["skipped"] = "No period set: kept for ever."
        return plan
    cutoff = now - timedelta(days=rule.keep_days)
    plan["older_than"] = cutoff.isoformat()
    rows = kind.rows(cutoff, now)
    whole, people = _holds_on(kind.key, holds)
    if whole:
        plan["skipped"] = "A legal hold covers all of these."
        plan["held"] = rows.count()
        return plan
    if people and kind.about is not None:
        about = kind.about(people)
        plan["held"] = rows.filter(about).count()
        rows = rows.exclude(about)
    plan["rows"] = rows
    return plan


def _counted(kind: Category, rule: RetentionRule, holds, now) -> dict:
    plan = _plan(kind, rule, holds, now)
    rows = plan.pop("rows")
    plan["would_delete"] = rows.count() if rows is not None else 0
    return plan


def preview(now=None) -> dict[str, dict]:
    """Per kind: how many rows the purge would delete now and how many holds keep."""
    now = now or timezone.now()
    holds = _active_holds()
    rules = {rule.category: rule for rule in RetentionRule.objects.all()}
    return {
        key: _counted(kind, rules.get(key) or _rule(key), holds, now)
        for key, kind in CATEGORIES.items()
    }


def preview_one(rule: RetentionRule) -> dict:
    """The same for one kind (the console's list shows a row per kind)."""
    return _counted(_category(rule.category), rule, _active_holds(), timezone.now())


def batch_ids(rows: QuerySet) -> QuerySet:
    """The next batch to delete. Any order will do, so none is asked for: the database can then
    use the index on the cut-off column instead of walking the whole table (HIMS-DATA-002)."""
    return rows.order_by().values_list("pk", flat=True)[:DELETE_BATCH]


def _delete(rows: QuerySet) -> tuple[int, bool]:
    """Delete in small transactions, at most RUN_LIMIT rows; (deleted, more left)."""
    deleted = 0
    model = rows.model
    while deleted < RUN_LIMIT:
        ids = list(batch_ids(rows))
        if not ids:
            return deleted, False
        with transaction.atomic():
            count, _ = model.objects.filter(pk__in=ids).delete()
        deleted += count
    return deleted, rows.exists()


def run_purge(*, trigger, actor=None, request=None, now=None) -> RetentionPurgeRun:
    """Apply waiting periods, then delete what the rules allow, honouring every active hold.
    One run at a time (a database lock); the run and the audit event record the counts."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [_PURGE_LOCK])
        if not cursor.fetchone()[0]:
            raise ConflictError("A purge is already running. Try again later.", code="BUSY")
    try:
        started = timezone.now()
        now = now or started
        applied = apply_due_periods(now)
        holds = _active_holds()
        details, total = {}, 0
        for key, kind in CATEGORIES.items():
            plan = _plan(kind, _rule(key), holds, now)
            rows = plan.pop("rows")
            plan["deleted"], plan["more_left"] = _delete(rows) if rows is not None else (0, False)
            plan["period_applied_now"] = key in applied
            total += plan["deleted"]
            details[key] = plan
        run = RetentionPurgeRun.objects.create(
            started_at=started,
            finished_at=timezone.now(),
            trigger=trigger,
            run_by=actor,
            deleted_total=total,
            details=details,
        )
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [_PURGE_LOCK])
    record_audit_event(
        action=AuditAction.RETENTION_PURGE_RUN,
        resource_type="retention_purge_run",
        resource_id=run.pk,
        actor=actor,
        request=request,
        metadata={
            "trigger": trigger,
            "deleted_total": total,
            "deleted": {key: plan["deleted"] for key, plan in details.items()},
            "held": {key: plan["held"] for key, plan in details.items() if plan["held"]},
            "active_holds": len(holds),
        },
    )
    logger.info("retention_purge_run", extra={"deleted_total": total, "trigger": trigger})
    return run
