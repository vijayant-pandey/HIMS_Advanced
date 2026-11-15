"""The high-volume queries HIMS runs, and the index each one must use (spec 28.6; HIMS-DATA-002;
patients and the MPI: HIMS-DATA-003).

Each entry builds the same query the app builds (often by calling the app's own code), so the
check follows the code when it changes. ``indexes`` lists the index names that serve it; a name
ending in ``_`` is a prefix (Django adds a hash to the names of foreign-key indexes).

Adding a high-volume query to the app? Add it here with its index, and to the table in
docs/architecture/data-architecture/README.md section 4 (a test keeps the two in step).
"""

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Q, QuerySet
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
    # Where the Performance screen groups it; by default from the table.
    area: str = ""

    @property
    def area_label(self) -> str:
        return self.area or area_of_table(self.table)


# The Performance screen groups queries and screens by these areas.
PATIENTS = "Patients"
AUDIT = "Audit log"
STAFF = "Staff and rota"
HOSPITAL = "Hospital set-up and beds"
ACCESS = "Sign-in and access"
PLATFORM = "Platform and compliance"
CONSOLE = "Admin console"
OPD = "Outpatient (OPD)"

_TABLE_AREAS = {
    "audit_events": AUDIT,
    "role_assignments": ACCESS,
    "user_sessions": ACCESS,
    "user_password_resets": ACCESS,
    "staff_credentials": STAFF,
    "shifts": STAFF,
    "beds": HOSPITAL,
    "doctor_schedules": OPD,
    "schedule_exceptions": OPD,
    "appointments": OPD,
}


def area_of_table(table: str) -> str:
    if table.startswith("patient"):
        return PATIENTS
    return _TABLE_AREAS.get(table, PLATFORM)


def _patient_samples(first) -> dict:
    """A real patient, phone, ID number and emergency access to look for (HIMS-DATA-003)."""
    from django.db.models import Count

    from apps.patients.models import EmergencyAccess, Patient, PatientContact, PatientIdentifier

    patient_id, mrn, names = first(
        Patient.objects.order_by().filter(is_restricted=False), "pk", "mrn", "search_name"
    )
    # The commonest family name: the slowest one-word search (as Kumar or Devi would be).
    common = (
        Patient.objects.exclude(family_name="")
        .values("family_name")
        .annotate(people=Count("pk"))
        .order_by("-people")
        .values_list("family_name", flat=True)
        .first()
    )
    (phone,) = first(PatientContact.objects.order_by().exclude(phone=""), "phone")
    # A personal ID number (Aadhaar, ABHA, passport...): previous MRNs are searched per hospital.
    id_kind, id_hash = first(
        PatientIdentifier.objects.order_by().exclude(kind=PatientIdentifier.Kind.PREVIOUS_MRN),
        "kind",
        "value_hash",
    )
    access_user_id, access_patient_id = first(
        EmergencyAccess.objects.order_by(), "user_id", "patient_id"
    )
    words = (names or "synthetic patient").split()
    number = re.search(r"(\d+)$", mrn or "")
    return {
        "patient_id": patient_id or uuid.uuid4(),
        "mrn": mrn or "MRN-00000000",
        "mrn_number": str(int(number.group(1))) if number else "1",
        "phone": phone or "+910000000000",
        "id_kind": id_kind or "passport",
        "id_hash": id_hash or "0" * 64,
        "name_words": words[:2],
        "family_word": [common.casefold()] if common else words[-1:],
        "access_user_id": access_user_id or uuid.uuid4(),
        "access_patient_id": access_patient_id or uuid.uuid4(),
    }


def pick_samples() -> dict:
    """Real values to search for (a person who has sign-ins, a department with shifts...), so the
    plans are the ones real searches get. Falls back to random ids on an empty database."""
    from apps.audit.models import AuditEvent
    from apps.beds.models import Bed
    from apps.identity.models import User, UserSession
    from apps.organizations.dates import hospital_today
    from apps.rosters.models import Shift
    from apps.scheduling.models import Appointment, DoctorSchedule

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
    opd_department_id, opd_staff_id, opd_facility_id = first(
        DoctorSchedule.objects.order_by(), "department_id", "staff_id", "facility_id"
    )
    booked_staff_id, booked_patient_id, booked_department_id = first(
        Appointment.objects.filter(status="booked").order_by(),
        "staff_id",
        "patient_id",
        "department_id",
    )
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
        "opd_department_id": opd_department_id or uuid.uuid4(),
        "opd_staff_id": opd_staff_id or uuid.uuid4(),
        "opd_facility_id": opd_facility_id or uuid.uuid4(),
        "booked_staff_id": booked_staff_id or uuid.uuid4(),
        "booked_patient_id": booked_patient_id or uuid.uuid4(),
        "booked_department_id": booked_department_id or uuid.uuid4(),
        **_patient_samples(first),
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


def _opd_week(samples, **who):
    """The weekly sessions behind one week of the OPD schedule (apps.scheduling.availability)."""
    from apps.scheduling.models import DoctorSchedule

    today = samples["today"]
    return DoctorSchedule.objects.filter(
        Q(valid_until__isnull=True) | Q(valid_until__gte=today),
        is_active=True,
        valid_from__lte=today + timedelta(days=6),
        **who,
    )


def _opd_department(samples):
    return _opd_week(samples, department_id=samples["opd_department_id"])


def _opd_doctor(samples):
    return _opd_week(samples, staff_id__in=[samples["opd_staff_id"]])


def _opd_exceptions(samples, **where):
    from apps.scheduling.models import ScheduleException

    today = samples["today"]
    return ScheduleException.objects.filter(
        status=ScheduleException.Status.ACTIVE,
        start_date__lte=today + timedelta(days=6),
        end_date__gte=today,
        **where,
    )


def _opd_away(samples):
    return _opd_exceptions(samples, kind="leave", staff_id__in=[samples["opd_staff_id"]])


def _opd_holidays(samples):
    return _opd_exceptions(samples, kind="holiday", facility_id__in=[samples["opd_facility_id"]])


def _opd_bookings(samples):
    """A week of one doctor's appointments, put into their sessions (availability)."""
    from apps.scheduling.models import ACTIVE_STATUSES, Appointment

    today = samples["today"]
    return Appointment.objects.filter(
        staff_id__in=[samples["booked_staff_id"]],
        local_date__gte=today,
        local_date__lte=today + timedelta(days=6),
        status__in=ACTIVE_STATUSES,
    )


def _patient_appointments(samples):
    """A patient's upcoming appointments (chart Overview; the clash check when booking)."""
    from apps.scheduling.models import ACTIVE_STATUSES, Appointment

    return Appointment.objects.filter(
        patient_id=samples["booked_patient_id"],
        status__in=ACTIVE_STATUSES,
        ends_at__gt=samples["now"],
    ).order_by("starts_at")[:200]


def _appointments_to_move(samples):
    """Booked appointments still to come in one department (the "To move" list)."""
    from apps.scheduling.models import Appointment

    today = samples["today"]
    return Appointment.objects.filter(
        local_date__gte=today,
        local_date__lte=today + timedelta(days=180),
        status="booked",
        department_id=samples["booked_department_id"],
        starts_at__gte=samples["now"],
    ).order_by("starts_at")


def _appointments_newest(samples):
    """The console's list of appointments, newest first (Django adds the id)."""
    from apps.scheduling.models import Appointment

    return Appointment.objects.order_by("-starts_at", "-pk")[:100]


def _bed_board(samples):
    from apps.beds.models import Bed

    return Bed.objects.filter(facility_id=samples["facility_id"], is_active=True)


# --- Patients and the MPI (HIMS-DATA-003) ------------------------------------------------------


def _patient_list(samples):
    """The patient list as most people see it: newest registrations, restricted ones hidden."""
    from apps.patients.models import Patient

    return Patient.objects.filter(is_restricted=False).order_by("-created_at")[:25]


def _patient_list_facility(samples):
    from apps.patients.models import Patient

    return Patient.objects.filter(
        registered_facility_id=samples["facility_id"], is_restricted=False
    ).order_by("-created_at")[:25]


def _patient_by_mrn(samples):
    from apps.patients import search

    return search.mrn_matches(samples["mrn"])


def _patient_by_merged_mrn(samples):
    from apps.patients import search

    return search.merged_mrn_matches(samples["mrn"])


def _patient_by_mrn_number(samples):
    from apps.patients import search

    return search.mrn_number_matches(samples["mrn_number"])


def _patient_by_phone(samples):
    from apps.patients import search

    return search.phone_matches(samples["phone"])


def _patient_by_id_number(samples):
    from apps.patients.models import PatientIdentifier

    # The filter search.identifier_query builds for a valid number: kind and fingerprint.
    return PatientIdentifier.objects.filter(
        kind=samples["id_kind"], value_hash__in=[samples["id_hash"]], is_active=True
    )


def _patient_previous_mrn_issuers(samples):
    from apps.patients import search

    return search.previous_mrn_issuers()


def _issued_numbers_newest(samples):
    """The console's list of every number issued, newest first (Django adds the id)."""
    from apps.numbering.models import IssuedNumber

    return IssuedNumber.objects.order_by("-created_at", "-pk")[:100]


def _patient_by_name(key):
    def build(samples):
        from apps.patients import search
        from apps.patients.models import Patient

        found = search.by_name(Patient.objects.filter(is_restricted=False), samples[key])
        return found[: search.MAX_RESULTS]

    return build


def _patient_consents(samples):
    from apps.patients.models import PatientConsent

    return PatientConsent.objects.filter(patient_id=samples["patient_id"]).order_by("-created_at")


def _patient_history(samples):
    from apps.patients import chart
    from apps.patients.models import Patient

    return chart.history(Patient(pk=samples["patient_id"]))[:25]


def _emergency_open(samples):
    from apps.patients import restricted

    return restricted.open_accesses(samples["access_user_id"], samples["access_patient_id"])[:1]


def _emergency_to_review(samples):
    from apps.patients import restricted
    from apps.patients.models import EmergencyAccess

    waiting = restricted.in_state(EmergencyAccess.objects.all(), restricted.State.TO_REVIEW)
    return waiting.order_by("-created_at")[:25]


def _restricted_openings(samples):
    from apps.patients import restricted

    return restricted.restricted_openings(samples["now"] - timedelta(days=7))[:25]


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
        # MRNs are most numbers issued: walking every number newest first and skipping the
        # others is as quick (HIMS-DATA-003 added that index); the budget catches a slow plan.
        also=("issued_numbers_created_idx",),
    ),
    QueryCheck(
        "issued_numbers_newest",
        "Numbering: every number issued, newest first (console list)",
        "issued_numbers",
        ("issued_numbers_created_idx",),
        _issued_numbers_newest,
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
        "opd_department_week",
        "OPD schedule: one department's sessions",
        "doctor_schedules",
        ("doctor_schedules_department_id_",),
        _opd_department,
    ),
    QueryCheck(
        "opd_doctor_week",
        "OPD schedule: one doctor's sessions",
        "doctor_schedules",
        ("doctor_schedule_staff_idx", "doctor_schedule_no_overlap"),
        _opd_doctor,
    ),
    QueryCheck(
        "opd_doctor_away",
        "OPD schedule: a doctor's time away",
        "schedule_exceptions",
        ("schedule_exception_staff_idx",),
        _opd_away,
    ),
    QueryCheck(
        "opd_holidays",
        "OPD schedule: a facility's holidays",
        "schedule_exceptions",
        ("schedule_exception_fac_idx",),
        _opd_holidays,
    ),
    QueryCheck(
        "opd_bookings",
        "Appointments: one doctor's week, in their sessions",
        "appointments",
        ("appointment_staff_day_idx", "appointment_no_double_booking"),
        _opd_bookings,
    ),
    QueryCheck(
        "patient_appointments",
        "Appointments: one patient's upcoming ones",
        "appointments",
        ("appointment_patient_idx",),
        _patient_appointments,
    ),
    QueryCheck(
        "appointments_to_move",
        "Appointments: one department's booked ones still to come (To move)",
        "appointments",
        ("appointment_booked_dept_idx",),
        _appointments_to_move,
    ),
    QueryCheck(
        "appointments_newest",
        "Appointments: every appointment, newest first (console list)",
        "appointments",
        ("appointment_start_idx",),
        _appointments_newest,
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
    # Patients and the MPI (HIMS-DATA-003; spec 28.6: "patient exact match by
    # organization-scoped identifier", "patient search by approved demographic/search index").
    QueryCheck(
        "patient_list",
        "Patients: newest registrations first (the list's first page)",
        "patients",
        ("patients_created_idx",),
        _patient_list,
    ),
    QueryCheck(
        "patient_list_facility",
        "Patients registered at one facility, newest first",
        "patients",
        ("patients_facility_idx",),
        _patient_list_facility,
        # Most patients are registered at the main branch: walking the newest patients and
        # skipping other branches is as quick there; the budget catches a slow plan.
        also=("patients_created_idx",),
    ),
    QueryCheck(
        "patient_by_mrn",
        "Patient search: exact MRN",
        "patients",
        ("patients_mrn_unique",),
        _patient_by_mrn,
        # A new hospital's few patients, before PostgreSQL has statistics, may be read through
        # the hospital's own index (one hospital: every row); at volume that reads every patient
        # and fails the time budget.
        also=("patients_organization_id_",),
    ),
    QueryCheck(
        "patient_by_merged_mrn",
        "Patient search: an earlier MRN kept after a merge",
        "patient_aliases",
        ("patient_aliases_merged_mrn_idx",),
        _patient_by_merged_mrn,
    ),
    QueryCheck(
        "patient_by_mrn_number",
        "Patient search: the number part of the MRN (“123” finds MRN-00000123)",
        "patients",
        ("patients_mrn_number_idx",),
        _patient_by_mrn_number,
    ),
    QueryCheck(
        "patient_by_phone",
        "Patient search: phone number",
        "patient_contacts",
        ("patient_contacts_phone_idx",),
        _patient_by_phone,
    ),
    QueryCheck(
        "patient_by_id_number",
        "Patient search: ID number (by its fingerprint)",
        "patient_identifiers",
        ("patient_identifiers_hash_idx", "patient_identifiers_unique_number"),
        _patient_by_id_number,
    ),
    QueryCheck(
        "patient_previous_mrn_issuers",
        "Patient search: hospitals with previous MRNs on record (a number not found otherwise)",
        "patient_identifiers",
        ("patient_ids_prev_mrn_idx",),
        _patient_previous_mrn_issuers,
    ),
    QueryCheck(
        "patient_by_name",
        "Patient search: given and family name (similar spelling or sound)",
        "patients",
        ("patients_search_name_trgm", "patients_search_sounds_idx"),
        _patient_by_name("name_words"),
    ),
    QueryCheck(
        "patient_by_family_name",
        "Patient search: one name only (a common family name)",
        "patients",
        ("patients_search_name_trgm", "patients_search_sounds_idx"),
        _patient_by_name("family_word"),
        # The worst case: the commonest family name (1 patient in 17, 30,000 at hospital size),
        # every match ranked by closeness. Both indexes are used; the ranking grows with the
        # matches: 220 to 360 ms measured at 500,000 patients before the sound key was checked
        # first, its screen within 500 ms (HIMS-DATA-003; a nearest-first index for larger
        # registers: HIMS-PAT-009).
        budget_ms=400.0,
    ),
    QueryCheck(
        "patient_consents",
        "Patient record: consent decisions, newest first",
        "patient_consents",
        ("patient_consents_idx", "patient_consents_patient_id_"),
        _patient_consents,
    ),
    QueryCheck(
        "patient_history",
        "Patient record history: who opened and changed it",
        "audit_events",
        ("audit_resource_idx",),
        _patient_history,
        area=PATIENTS,
    ),
    QueryCheck(
        "patient_emergency_open",
        "Restricted record: is my emergency access open? (every opening)",
        "patient_emergency_access",
        ("patient_emergency_user_idx",),
        _emergency_open,
    ),
    QueryCheck(
        "patient_emergency_to_review",
        "Emergency access waiting for review, newest first",
        "patient_emergency_access",
        ("patient_emergency_review_idx",),
        _emergency_to_review,
    ),
    QueryCheck(
        "patient_restricted_openings",
        "Restricted record openings in the last 7 days (medical records)",
        "audit_events",
        ("audit_action_idx",),
        _restricted_openings,
        also=("audit_occurred_idx",),
        area=PATIENTS,
    ),
)
