"""The high-volume queries HIMS runs, and the index each one must use (spec 28.6; HIMS-DATA-002).

Each entry builds the same query the app builds (often by calling the app's own code), so the
check follows the code when it changes. ``indexes`` lists the index names that serve it; a name
ending in ``_`` is a prefix (Django adds a hash to the names of foreign-key indexes).

Adding a high-volume query to the app? Add it here with its index, and to the table in
docs/architecture/data-architecture/README.md section 4 (a test keeps the two in step).
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import QuerySet
from django.utils import timezone


@dataclass(frozen=True)
class QueryCheck:
    key: str
    label: str
    table: str
    indexes: tuple[str, ...]
    build: Callable[[dict], QuerySet]
    # The longest one run of the query may take at volume (EXPLAIN ANALYZE execution time).
    budget_ms: float = 100.0
    # Another index the database may rightly prefer, depending on how many rows match (a common
    # kind of event: walking the newest events finds 25 matches at once). The time budget still
    # catches a slow plan at volume.
    also: tuple[str, ...] = ()
    # A batch to delete: while most rows are past the cut-off, reading the table from the start
    # fills a batch at once, which is right; the index must still be chosen once full reads are
    # ruled out, for the steady state where only a day's rows are past it.
    batch: bool = False


def pick_samples() -> dict:
    """Real values to search for (a person who has sign-ins, a department with shifts...), so the
    plans are the ones real searches get. Falls back to random ids on an empty database."""
    from apps.audit.models import AuditEvent
    from apps.beds.models import Bed
    from apps.identity.models import User, UserSession
    from apps.organizations.dates import hospital_today
    from apps.rosters.models import Shift

    def first(queryset, *fields):
        row = queryset.values_list(*fields).first()
        return row if row else (None,) * len(fields)

    now = timezone.now()
    (user_id,) = first(UserSession.objects.order_by(), "user_id")
    if user_id is None:
        (user_id,) = first(User.objects.order_by(), "pk")
    (actor_id,) = first(AuditEvent.objects.order_by().exclude(actor_id=None), "actor_id")
    resource_type, resource_id, action = first(
        AuditEvent.objects.order_by().exclude(resource_id=""),
        "resource_type",
        "resource_id",
        "action",
    )
    department_id, staff_id = first(Shift.objects.order_by(), "department_id", "staff_id")
    (facility_id,) = first(Bed.objects.order_by(), "facility_id")
    return {
        "now": now,
        "today": hospital_today(),  # the hospital's calendar day, not the server's
        "user_id": user_id or uuid.uuid4(),
        "actor_id": actor_id or uuid.uuid4(),
        "resource_type": resource_type or "staff_member",
        "resource_id": resource_id or str(uuid.uuid4()),
        "action": action or "auth.login.succeeded",
        "department_id": department_id or uuid.uuid4(),
        "staff_id": staff_id or uuid.uuid4(),
        "facility_id": facility_id or uuid.uuid4(),
    }


# --- Builders: the app's own queries ---------------------------------------------------------


def _audit(samples, **filters):
    from apps.audit.api.views import with_names
    from apps.audit.models import AuditEvent

    return with_names(AuditEvent.objects.filter(**filters)).order_by("-occurred_at")[:25]


def _audit_day(samples):
    end = samples["now"]
    return _audit(samples, occurred_at__gte=end - timedelta(days=1), occurred_at__lt=end)


def _seal_next(samples):
    from apps.audit.integrity import HASHED_FIELDS, _last_link, _pending

    return _pending(_last_link()).order_by("occurred_at", "id").values(*HASHED_FIELDS)[:1000]


def _waiting_to_seal(samples):
    from apps.audit.integrity import sealing_window_start, unsealed_events

    start = sealing_window_start()
    waiting = unsealed_events()
    return waiting.filter(occurred_at__gte=start) if start is not None else waiting


def _grants(samples):
    from apps.access_control.selectors import _active_assignments
    from apps.identity.models import User

    return _active_assignments(User(pk=samples["user_id"])).values_list(
        "role__role_permissions__permission__codename", "facility_id", "department_id"
    )


def _my_sign_ins(samples):
    from apps.identity.models import User
    from apps.identity.sessions import open_sessions_for

    return open_sessions_for(User(pk=samples["user_id"]))


def _session_by_key(samples):
    from apps.identity.models import UserSession

    return UserSession.objects.filter(session_key="volumecheck0000000000000000000000000000")


def _reset_rate(samples):
    from apps.identity.models import PasswordReset

    return PasswordReset.objects.filter(
        user_id=samples["user_id"], created_at__gte=samples["now"] - timedelta(hours=1)
    )


def _messages(samples):
    from apps.notifications.models import Notification

    return Notification.objects.order_by("-created_at")[:25]


def _messages_retry(samples):
    from apps.notifications.models import Notification

    return Notification.objects.filter(
        status=Notification.Status.FAILED, next_attempt_at__lte=samples["now"]
    ).order_by("next_attempt_at")[:50]


def _outbox_pending(samples):
    from common.outbox.models import OutboxEvent

    return OutboxEvent.objects.filter(
        status=OutboxEvent.Status.PENDING, available_at__lte=samples["now"]
    ).order_by("occurred_at")[:100]


def _outbox_failed(samples):
    from common.outbox.models import OutboxEvent

    return OutboxEvent.objects.filter(status=OutboxEvent.Status.DEAD)


def _outbox_cleanup(samples):
    from django.conf import settings
    from django.db.models import Q

    from common.outbox.models import OutboxEvent

    cutoff = samples["now"] - timedelta(days=settings.HIMS_OUTBOX_RETENTION_DAYS)
    Status = OutboxEvent.Status
    return (
        OutboxEvent.objects.filter(
            Q(status=Status.PUBLISHED, published_at__lt=cutoff)
            | Q(status=Status.DISMISSED, resolved_at__lt=cutoff)
        )
        .order_by("pk")
        .values_list("pk", flat=True)[:500]
    )


def _idempotency_expired(samples):
    from common.idempotency.models import IdempotencyRecord

    return IdempotencyRecord.objects.filter(expires_at__lt=samples["now"])


def _issued_numbers(samples):
    from apps.numbering.models import IssuedNumber

    return IssuedNumber.objects.filter(document_type="mrn").order_by("-created_at")[:25]


def _licences_expiring(samples):
    from apps.staff.models import StaffCredential

    today = samples["today"]
    return StaffCredential.objects.filter(
        expires_at__gte=today, expires_at__lte=today + timedelta(days=90)
    ).order_by("expires_at")


def _rota_department(samples):
    from apps.rosters.models import Shift

    today = samples["today"]
    return Shift.objects.filter(
        department_id=samples["department_id"],
        on_date__gte=today,
        on_date__lt=today + timedelta(days=7),
    )


def _rota_person(samples):
    from apps.rosters.models import Shift

    today = samples["today"]
    return Shift.objects.filter(
        staff_id=samples["staff_id"], on_date__gte=today, on_date__lt=today + timedelta(days=7)
    )


def _bed_board(samples):
    from apps.beds.models import Bed

    return Bed.objects.filter(facility_id=samples["facility_id"], is_active=True)


def _retention(key):
    def build(samples):
        from apps.compliance.retention import CATEGORIES, batch_ids

        cutoff = samples["now"] - timedelta(days=CATEGORIES[key].minimum_days)
        return batch_ids(CATEGORIES[key].rows(cutoff, samples["now"]))

    return build


QUERIES: tuple[QueryCheck, ...] = (
    QueryCheck(
        "audit_newest",
        "Audit log: newest events first (the screen's first page)",
        "audit_events",
        ("audit_occurred_idx",),
        lambda s: _audit(s),
    ),
    QueryCheck(
        "audit_by_person",
        "Audit log: one person's actions",
        "audit_events",
        ("audit_actor_idx",),
        lambda s: _audit(s, actor_id=s["actor_id"]),
        also=("audit_occurred_idx",),
    ),
    QueryCheck(
        "audit_by_record",
        "Audit log: everything that happened to one record",
        "audit_events",
        ("audit_resource_idx",),
        lambda s: _audit(s, resource_type=s["resource_type"], resource_id=s["resource_id"]),
    ),
    QueryCheck(
        "audit_by_type",
        "Audit log: one kind of event",
        "audit_events",
        ("audit_action_idx",),
        lambda s: _audit(s, action=s["action"]),
        also=("audit_occurred_idx",),
    ),
    QueryCheck(
        "audit_by_day",
        "Audit log: one day",
        "audit_events",
        ("audit_occurred_idx",),
        _audit_day,
    ),
    QueryCheck(
        "audit_seal_next",
        "Audit sealing: the next 1,000 events to seal (every minute)",
        "audit_events",
        ("audit_chain_entries_event_id_key",),
        _seal_next,
        budget_ms=250.0,  # a batch of 1,000 for a background job, not a screen
    ),
    QueryCheck(
        "audit_waiting_to_seal",
        "Audit integrity: events waiting to be sealed",
        "audit_events",
        ("audit_chain_entries_event_id_key",),
        _waiting_to_seal,
    ),
    QueryCheck(
        "access_grants",
        "A person's current access (every request)",
        "role_assignments",
        ("role_assignment_user_idx", "role_assignment_active_unique", "role_assignments_user_id_"),
        _grants,
    ),
    QueryCheck(
        "session_by_key",
        "Sign-in register: the current browser's sign-in",
        "user_sessions",
        ("user_sessions_session_key_",),  # the unique index or its pattern twin
        _session_by_key,
    ),
    QueryCheck(
        "my_sign_ins",
        "My sign-ins: a person's open sign-ins",
        "user_sessions",
        ("user_session_open_idx", "user_sessions_user_id_"),
        _my_sign_ins,
        # Starting from the few live browser sessions and looking each one up is as quick.
        also=("user_sessions_session_key_",),
    ),
    QueryCheck(
        "password_reset_rate",
        "Password reset: requests by one person in the last hour (rate limit)",
        "user_password_resets",
        ("password_reset_user_idx", "user_password_resets_user_id_"),
        _reset_rate,
    ),
    QueryCheck(
        "messages_newest",
        "Messages: newest first",
        "notifications",
        ("notification_created_idx",),
        _messages,
    ),
    QueryCheck(
        "messages_retry",
        "Messages: failed ones due to be sent again (background job)",
        "notifications",
        ("notification_retry_idx",),
        _messages_retry,
    ),
    QueryCheck(
        "outbox_pending",
        "Background jobs: events waiting to be sent (every few seconds)",
        "outbox_events",
        ("outbox_pending_idx",),
        _outbox_pending,
    ),
    QueryCheck(
        "outbox_failed",
        "Background jobs: failed events needing a decision (health page)",
        "outbox_events",
        ("outbox_attention_idx",),
        _outbox_failed,
    ),
    QueryCheck(
        "outbox_cleanup",
        "Background jobs: old events to clean up (daily)",
        "outbox_events",
        ("outbox_published_idx", "outbox_events_pkey"),
        _outbox_cleanup,
    ),
    QueryCheck(
        "idempotency_expired",
        "Repeated-request records past 48 hours (hourly clean-up)",
        "idempotency_records",
        ("idempotency_expiry_idx",),
        _idempotency_expired,
    ),
    QueryCheck(
        "issued_numbers",
        "Numbering: numbers issued for one document type, newest first",
        "issued_numbers",
        ("issued_numbers_type_idx",),
        _issued_numbers,
    ),
    QueryCheck(
        "licences_expiring",
        "Licence expiry: licences ending in the next 90 days (daily alerts)",
        "staff_credentials",
        ("staff_credential_expiry_idx",),
        _licences_expiring,
    ),
    QueryCheck(
        "rota_department",
        "Rota: one department's week",
        "shifts",
        ("shift_department_day_idx",),
        _rota_department,
    ),
    QueryCheck(
        "rota_person",
        "Rota: one person's week",
        "shifts",
        ("shift_staff_day_idx", "shift_no_overlap_per_person"),
        _rota_person,
    ),
    QueryCheck(
        "bed_board",
        "Bed board: one facility's beds",
        "beds",
        ("beds_board_idx", "beds_type_idx", "beds_facility_id_"),
        _bed_board,
    ),
    QueryCheck(
        "retention_sign_ins",
        "Retention purge: ended sign-ins older than the period",
        "user_sessions",
        ("user_session_ended_idx",),
        _retention("sign_ins"),
        batch=True,
    ),
    QueryCheck(
        "retention_messages",
        "Retention purge: finished messages older than the period",
        "notifications",
        ("notification_created_idx",),
        _retention("messages"),
        # Nearly every message is finished, so the status-first index serves it as well.
        also=("notification_retry_idx",),
        batch=True,
    ),
)
