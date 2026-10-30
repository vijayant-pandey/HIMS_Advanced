"""Periodic access reviews (HIMS-IAM-012; spec 4.4, 13.2 "periodic permission review").

A reviewer starts a review; HIMS copies everyone's current access into it (one item per role
assignment). Reviewers keep or remove each item. Removing revokes the assignment through the
normal service, in the same transaction, so access ends at once. Nobody reviews their own
access. A review can only be completed when every item is decided; the completed review is the
evidence auditors download. A daily job emails reviewers when a review is due or overdue.
"""

from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.audit.services import AuditAction, record_audit_event
from apps.notifications.services import send_email
from common.concurrency import bump_version, lock_for_update
from common.exceptions import ConflictError

from .catalog import P
from .models import AccessReview, AccessReviewItem, AccessReviewReminder, RoleAssignment
from .services import revoke_role_assignment

Decision = AccessReviewItem.Decision

# Most items one request may decide (keeps a single transaction reasonable).
MAX_ITEMS_PER_DECISION = 500


def current_assignments():
    """Every role assignment that gives access right now."""
    now = timezone.now()
    return (
        RoleAssignment.objects.filter(revoked_at__isnull=True, valid_from__lte=now)
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
        .select_related("user", "role", "facility", "department", "delegation__delegator")
    )


def role_label(assignment: RoleAssignment) -> str:
    """Role name; access lent for cover says so, so reviewers can tell it apart (HIMS-IAM-017)."""
    name = assignment.role.name
    if assignment.delegation_id is not None:
        until = timezone.localtime(assignment.delegation.ends_at).strftime("%d %b %Y")
        name = f"{name} (cover for {assignment.delegation.delegator.display_name} until {until})"
    return name[:128]


def scope_label(assignment: RoleAssignment) -> str:
    if assignment.department_id:
        return f"{assignment.facility.name} / {assignment.department.name}"
    if assignment.facility_id:
        return assignment.facility.name
    return "Whole hospital"


def _assignment_is_current(assignment: RoleAssignment, now=None) -> bool:
    now = now or timezone.now()
    return assignment.revoked_at is None and (
        assignment.valid_until is None or assignment.valid_until > now
    )


def ensure_can_start(*, due_on: date | None) -> date:
    """Checks before starting a review; returns the finish-by date (default 14 days)."""
    if AccessReview.objects.filter(status=AccessReview.Status.OPEN).exists():
        raise ConflictError(
            "An access review is already in progress. Complete or cancel it first.",
            code="REVIEW_ALREADY_OPEN",
        )
    today = timezone.localdate()
    if due_on is not None and due_on < today:
        raise ConflictError("The finish-by date cannot be in the past.", code="DUE_DATE_PAST")
    return due_on or today + timedelta(days=settings.HIMS_ACCESS_REVIEW_DEFAULT_DAYS_TO_FINISH)


@transaction.atomic
def start_review(*, actor, organization, title: str, due_on: date | None = None, request=None):
    due_on = ensure_can_start(due_on=due_on)
    review = AccessReview.objects.create(
        organization=organization, title=title.strip(), due_on=due_on, started_by=actor
    )
    items = [
        AccessReviewItem(
            review=review,
            assignment=a,
            person_name=a.user.display_name or a.user.email,
            person_email=a.user.email,
            account_active=a.user.is_active,
            last_signed_in_at=a.user.last_login,
            role_name=role_label(a),
            scope=scope_label(a),
            granted_at=a.valid_from,
            access_ends_at=a.valid_until,
        )
        for a in current_assignments()
    ]
    AccessReviewItem.objects.bulk_create(items)
    record_audit_event(
        action=AuditAction.ACCESS_REVIEW_STARTED,
        resource_type="access_review",
        resource_id=review.pk,
        actor=actor,
        request=request,
        metadata={"title": review.title, "items": len(items), "due_on": due_on.isoformat()},
    )
    return review


def _require_open(review: AccessReview) -> None:
    if review.status != AccessReview.Status.OPEN:
        raise ConflictError(
            f"This review is {review.get_status_display().lower()}; decisions cannot change.",
            code="REVIEW_CLOSED",
        )


@transaction.atomic
def decide_items(*, actor, review_id, item_ids, decision: str, comment: str = "", request=None):
    """Keep or remove access for the chosen items. Returns the updated items.

    Removing needs a comment (it becomes the revocation reason). An item whose access already
    ended elsewhere (e.g. the person left) is marked "already ended" instead.
    """
    if decision not in (Decision.KEEP, Decision.REMOVE):
        raise ValidationError({"decision": ["Choose keep or remove."]})
    comment = (comment or "").strip()
    if decision == Decision.REMOVE and not comment:
        raise ValidationError({"comment": ["Say why the access is removed."]})
    item_ids = list(dict.fromkeys(item_ids))
    if not item_ids or len(item_ids) > MAX_ITEMS_PER_DECISION:
        raise ValidationError(
            {"items": [f"Choose between 1 and {MAX_ITEMS_PER_DECISION} people to decide on."]}
        )
    review = AccessReview.objects.select_for_update().get(pk=review_id)
    _require_open(review)
    items = list(
        AccessReviewItem.objects.select_for_update(of=("self",))
        .filter(review=review, pk__in=item_ids)
        .select_related("assignment")
        .order_by()
    )
    if len(items) != len(item_ids):
        raise ValidationError({"items": ["Some of these people are not part of this review."]})
    if actor is not None and any(i.assignment.user_id == actor.pk for i in items):
        raise ConflictError(
            "You cannot review your own access. Another reviewer must decide it.",
            code="SELF_REVIEW",
        )
    now = timezone.now()
    counts = {Decision.KEEP: 0, Decision.REMOVE: 0, Decision.ENDED: 0}
    for item in items:
        if item.decision in (Decision.REMOVE, Decision.ENDED):
            continue  # access is already gone; nothing left to decide
        if not _assignment_is_current(item.assignment, now):
            item.decision = Decision.ENDED
        else:
            if decision == Decision.REMOVE:
                revoke_role_assignment(
                    actor=actor,
                    assignment_id=item.assignment_id,
                    reason=f"Access review “{review.title}”: {comment}",
                    request=request,
                )
            item.decision = decision
        item.decided_by = actor
        item.decided_at = now
        item.comment = comment
        item.save(update_fields=["decision", "decided_by", "decided_at", "comment"])
        counts[item.decision] += 1
    bump_version(review)
    review.save(update_fields=["version", "updated_at"])
    record_audit_event(
        action=AuditAction.ACCESS_REVIEW_DECIDED,
        resource_type="access_review",
        resource_id=review.pk,
        actor=actor,
        request=request,
        reason=comment,
        metadata={
            "decision": decision,
            "kept": counts[Decision.KEEP],
            "removed": counts[Decision.REMOVE],
            "already_ended": counts[Decision.ENDED],
            "items": [str(i.pk) for i in items],
        },
    )
    return items


def summary(review: AccessReview) -> dict:
    counts = dict(
        review.items.order_by()
        .values("decision")
        .annotate(n=Count("id"))
        .values_list("decision", "n")
    )
    return {d.value: counts.get(d.value, 0) for d in Decision}


@transaction.atomic
def complete_review(*, actor, review_id, version: int, notes: str = "", request=None):
    review = lock_for_update(AccessReview, pk=review_id, expected_version=version)
    _require_open(review)
    now = timezone.now()
    for item in review.items.filter(decision=Decision.PENDING).select_related("assignment"):
        if not _assignment_is_current(item.assignment, now):
            item.decision, item.decided_at = Decision.ENDED, now
            item.save(update_fields=["decision", "decided_at"])
    pending = review.items.filter(decision=Decision.PENDING).count()
    if pending:
        raise ConflictError(
            f"{pending} item(s) are not reviewed yet. Keep or remove each one first.",
            code="REVIEW_NOT_FINISHED",
        )
    review.status = AccessReview.Status.COMPLETED
    review.completed_at = now
    review.completed_by = actor
    review.notes = (notes or "").strip()
    bump_version(review)
    review.save(update_fields=["status", "completed_at", "completed_by", "notes", "updated_at"])
    record_audit_event(
        action=AuditAction.ACCESS_REVIEW_COMPLETED,
        resource_type="access_review",
        resource_id=review.pk,
        actor=actor,
        request=request,
        metadata={"title": review.title, **summary(review)},
    )
    return review


@transaction.atomic
def cancel_review(*, actor, review_id, version: int, reason: str, request=None):
    """Stop a review without finishing it. Decisions already made (incl. removals) stay."""
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": ["Say why the review is cancelled."]})
    review = lock_for_update(AccessReview, pk=review_id, expected_version=version)
    _require_open(review)
    review.status = AccessReview.Status.CANCELLED
    review.notes = reason
    bump_version(review)
    review.save(update_fields=["status", "notes", "updated_at"])
    record_audit_event(
        action=AuditAction.ACCESS_REVIEW_CANCELLED,
        resource_type="access_review",
        resource_id=review.pk,
        actor=actor,
        request=request,
        reason=reason,
        metadata={"title": review.title, **summary(review)},
    )
    return review


# --- Schedule and reminders -------------------------------------------------------------------


def schedule(today: date | None = None) -> dict:
    """When the next review is due: the interval after the last completed one (or after the
    hospital was set up, if none was ever completed)."""
    from apps.organizations.models import Organization

    today = today or timezone.localdate()
    interval = settings.HIMS_ACCESS_REVIEW_INTERVAL_DAYS
    last = (
        AccessReview.objects.filter(status=AccessReview.Status.COMPLETED)
        .order_by("-completed_at")
        .first()
    )
    if last is not None:
        base = timezone.localdate(last.completed_at)
    else:
        organization = Organization.objects.only("created_at").first()
        base = timezone.localdate(organization.created_at) if organization else today
    open_review = AccessReview.objects.filter(status=AccessReview.Status.OPEN).first()
    next_due_on = base + timedelta(days=interval)
    return {
        "interval_days": interval,
        "last_completed_at": last.completed_at if last else None,
        "next_due_on": next_due_on,
        "review_due": open_review is None and next_due_on <= today,
        "open_review_id": open_review.pk if open_review else None,
        "open_review_overdue": bool(open_review and open_review.due_on < today),
    }


def reviewer_emails() -> list[str]:
    now = timezone.now()
    emails = (
        RoleAssignment.objects.filter(
            Q(valid_until__isnull=True) | Q(valid_until__gt=now),
            revoked_at__isnull=True,
            valid_from__lte=now,
            user__is_active=True,
            role__role_permissions__permission__codename=P.ACCESS_REVIEWS_MANAGE,
        )
        .values_list("user__email", flat=True)
        .distinct()
    )
    return sorted(set(emails))


def send_access_review_reminders(today: date | None = None) -> int:
    """Email reviewers when a review is due or the one in progress is overdue. Each reminder
    is sent once (safe to run any number of times). Returns how many were sent."""
    from apps.organizations.models import Organization

    today = today or timezone.localdate()
    organization = Organization.objects.first()
    if organization is None:
        return 0
    plan = schedule(today)
    if plan["open_review_overdue"]:
        review = AccessReview.objects.get(pk=plan["open_review_id"])
        kind, due_on = AccessReviewReminder.Kind.OVERDUE, review.due_on
        subject = f"{organization.display_name}: the access review is overdue"
        body = (
            f"The access review “{review.title}” was due to finish on "
            f"{review.due_on:%d %b %Y}. {summary(review)['pending']} item(s) still need a "
            "decision.\n\nOpen HIMS → Access reviews to finish it.\n"
        )
    elif plan["review_due"]:
        review, kind, due_on = None, AccessReviewReminder.Kind.DUE, plan["next_due_on"]
        subject = f"{organization.display_name}: a periodic access review is due"
        body = (
            "It is time to check who has access to HIMS and remove access people no longer "
            f"need (due {due_on:%d %b %Y}; reviews are due every "
            f"{plan['interval_days']} days).\n\nOpen HIMS → Access reviews → "
            "Start a review.\n"
        )
    else:
        return 0
    recipients = reviewer_emails()
    try:
        with transaction.atomic():
            AccessReviewReminder.objects.create(
                organization=organization,
                kind=kind,
                due_on=due_on,
                review=review,
                recipients=len(recipients),
            )
            record_audit_event(
                action=AuditAction.ACCESS_REVIEW_REMINDER_SENT,
                resource_type="access_review",
                resource_id=review.pk if review else "",
                organization_id=organization.pk,
                metadata={
                    "kind": kind,
                    "due_on": due_on.isoformat(),
                    "recipients": len(recipients),
                },
            )
    except IntegrityError:
        return 0  # already sent
    if recipients:
        send_email(
            subject=subject,
            body=body,
            to=recipients,
            category="access",
            template="access.review_reminder",
        )
    return 1
