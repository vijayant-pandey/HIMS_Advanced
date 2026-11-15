"""Measure how fast the API answers the screens people use most (spec 18; HIMS-OPS-017).

Spec 18 sets the target "p95 below 300-500 ms for ordinary reads under expected load". HIMS
uses the strict end for pages that show one record or a short list (300 ms), and 500 ms for
searches and lists over the large tables (audit log, messages, staff, numbers).

How it measures: inside one database transaction that is rolled back at the end, a temporary
measuring account with administrator and auditor access is created, then each screen's API call
is made ``samples`` times in this process (Django's test client: the full middleware, sign-in,
permission and database work, but no network). p50/p95 are worked out per call, plus the number
of database queries one call makes. Because of the rollback nothing is left behind: no account,
no sign-in, no audit event. Only the result is kept (as a PerformanceCheck).

What it does not measure: the network, the web server's worker pool, and many people at once.
Those are measured against the hosted test environment before go-live (HIMS-OPS-021).
"""

import math
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote

from django.conf import settings
from django.core.cache import cache
from django.db import connection, transaction
from django.test import Client

from .queries import ACCESS, AUDIT, CONSOLE, HOSPITAL, OPD, PATIENTS, PLATFORM, STAFF

PAGE_MS = 300.0
SEARCH_MS = 500.0
DEFAULT_SAMPLES = 20
WARM_UP = 2
MAX_SAMPLES = 25  # stays under the per-person request limit (HIMS_THROTTLE_USER, 1200/min)
# Which area of the Performance screen a screen belongs to, by the start of its address.
_PATH_AREAS = (
    ("/admin/", CONSOLE),
    ("/api/v1/patient", PATIENTS),
    ("/api/v1/audit", AUDIT),
    ("/api/v1/staff", STAFF),
    ("/api/v1/rota", STAFF),
    ("/api/v1/doctor-schedules", OPD),
    ("/api/v1/availability", OPD),
    ("/api/v1/organization", HOSPITAL),
    ("/api/v1/facilities", HOSPITAL),
    ("/api/v1/departments", HOSPITAL),
    ("/api/v1/bed-board", HOSPITAL),
    ("/api/v1/auth", ACCESS),
    ("/api/v1/role", ACCESS),
)


def area_of_path(path: str) -> str:
    return next((area for start, area in _PATH_AREAS if path.startswith(start)), PLATFORM)


@dataclass(frozen=True)
class Endpoint:
    key: str
    label: str
    path: Callable[[dict], str]
    target_ms: float = PAGE_MS


def _fixed(path: str) -> Callable[[dict], str]:
    return lambda samples: path


def _patient_search(key: str) -> Callable[[dict], str]:
    """Patient search for a sample value (words are joined: a name)."""

    def path(samples: dict) -> str:
        value = samples[key]
        text = " ".join(value) if isinstance(value, list) else str(value)
        return f"/api/v1/patients/?search={quote(text)}"

    return path


ENDPOINTS: tuple[Endpoint, ...] = (
    Endpoint("me", "Who am I (every page load)", _fixed("/api/v1/auth/me/")),
    Endpoint("my_sign_ins", "My sign-ins", _fixed("/api/v1/auth/sessions/")),
    Endpoint("organization", "Hospital settings", _fixed("/api/v1/organization/")),
    Endpoint("facilities", "Facilities", _fixed("/api/v1/facilities/")),
    Endpoint("departments", "Departments", _fixed("/api/v1/departments/")),
    Endpoint(
        "bed_board",
        "Bed board (one facility)",
        lambda s: f"/api/v1/bed-board/?facility={s['facility_id']}",
        SEARCH_MS,
    ),
    Endpoint("staff", "Staff directory", _fixed("/api/v1/staff/"), SEARCH_MS),
    Endpoint(
        "staff_search", "Staff search by name", _fixed("/api/v1/staff/?search=0001"), SEARCH_MS
    ),
    Endpoint("licence_expiry", "Licence expiry", _fixed("/api/v1/staff-credentials/expiring/")),
    Endpoint(
        "rota",
        "Rota (one department's week)",
        lambda s: f"/api/v1/rota/?department={s['department_id']}&start={s['today']}",
        SEARCH_MS,
    ),
    Endpoint(
        "opd_week",
        "Doctor schedules (one department's week)",
        lambda s: (
            f"/api/v1/doctor-schedules/week/?department={s['opd_department_id']}&start={s['today']}"
        ),
    ),
    Endpoint(
        "opd_availability",
        "A doctor's free slots on one day",
        lambda s: f"/api/v1/availability/?doctor={s['opd_staff_id']}&date={s['today']}",
    ),
    Endpoint("roles", "Access: roles", _fixed("/api/v1/roles/")),
    Endpoint(
        "role_assignments",
        "Access: who has which role",
        _fixed("/api/v1/role-assignments/"),
        SEARCH_MS,
    ),
    Endpoint(
        "audit_newest", "Audit log (newest first)", _fixed("/api/v1/audit-events/"), SEARCH_MS
    ),
    Endpoint(
        "audit_by_person",
        "Audit log: one person",
        lambda s: f"/api/v1/audit-events/?actor_id={s['actor_id']}",
        SEARCH_MS,
    ),
    Endpoint(
        "audit_by_type",
        "Audit log: one kind of event",
        lambda s: f"/api/v1/audit-events/?action={s['action']}",
        SEARCH_MS,
    ),
    Endpoint(
        "audit_by_day",
        "Audit log: one day",
        lambda s: f"/api/v1/audit-events/?date_from={s['today']}&date_to={s['today']}",
        SEARCH_MS,
    ),
    Endpoint(
        "audit_by_name",
        "Audit log: search by a person's name",
        _fixed("/api/v1/audit-events/?person=Staff%20000123"),
        SEARCH_MS,
    ),
    Endpoint("messages", "Messages (emails and SMS)", _fixed("/api/v1/notifications/"), SEARCH_MS),
    Endpoint(
        "numbers", "Issued numbers", _fixed("/api/v1/issued-numbers/?document_type=mrn"), SEARCH_MS
    ),
    Endpoint(
        "background_jobs", "Background jobs: health", _fixed("/api/v1/background-jobs/health/")
    ),
    Endpoint("compliance", "Compliance summary", _fixed("/api/v1/compliance-summary/")),
    Endpoint(
        "retention",
        "Retention (with what a purge would delete)",
        _fixed("/api/v1/retention/"),
        SEARCH_MS,
    ),
    Endpoint("security", "Security status", _fixed("/api/v1/security/status/")),
    Endpoint(
        "integrity", "Audit integrity status", _fixed("/api/v1/audit-integrity-checks/status/")
    ),
    # Patients and the MPI (HIMS-DATA-003).
    Endpoint("patients", "Patients (newest first)", _fixed("/api/v1/patients/"), SEARCH_MS),
    Endpoint("patient_search_mrn", "Patient search: exact MRN", _patient_search("mrn"), SEARCH_MS),
    Endpoint(
        "patient_search_mrn_number",
        "Patient search: the number part of the MRN",
        _patient_search("mrn_number"),
        SEARCH_MS,
    ),
    Endpoint(
        "patient_search_phone", "Patient search: phone number", _patient_search("phone"), SEARCH_MS
    ),
    Endpoint(
        "patient_search_name",
        "Patient search: given and family name",
        _patient_search("name_words"),
        SEARCH_MS,
    ),
    Endpoint(
        "patient_search_family_name",
        "Patient search: one (common) family name",
        _patient_search("family_word"),
        SEARCH_MS,
    ),
    Endpoint(
        "patient_record",
        "Patient record (chart header and overview)",
        lambda s: f"/api/v1/patients/{s['patient_id']}/",
    ),
    Endpoint(
        "patient_history",
        "Patient record history",
        lambda s: f"/api/v1/patients/{s['patient_id']}/history/",
        SEARCH_MS,
    ),
    Endpoint(
        "emergency_access_to_review",
        "Emergency access waiting for review",
        _fixed("/api/v1/patient-emergency-access/?state=to_review"),
        SEARCH_MS,
    ),
    Endpoint(
        "restricted_openings",
        "Restricted record openings",
        _fixed("/api/v1/patients/restricted-openings/"),
        SEARCH_MS,
    ),
)

# The admin console's lists of the largest tables (ADR-016): the same targets as the app.
CONSOLE_ENDPOINTS: tuple[Endpoint, ...] = tuple(
    Endpoint(f"console_{key}", f"Console: {label}", _fixed(f"/admin/{path}/"), SEARCH_MS)
    for key, label, path in (
        ("audit", "audit events", "audit/auditevent"),
        ("sign_ins", "sign-ins", "identity/usersession"),
        ("messages", "messages", "notifications/notification"),
        ("outbox", "background events", "outbox/outboxevent"),
        ("numbers", "issued numbers", "numbering/issuednumber"),
        ("shifts", "shifts", "rosters/shift"),
        ("patients", "patients", "patients/patient"),
        ("emergency_access", "emergency access", "patients/emergencyaccess"),
        ("doctor_schedules", "doctor schedules", "scheduling/doctorschedule"),
    )
)


def all_endpoints() -> tuple[Endpoint, ...]:
    return ENDPOINTS + (CONSOLE_ENDPOINTS if settings.HIMS_ENABLE_ADMIN else ())


def percentile(values: list[float], share: float) -> float:
    """Nearest-rank percentile (p95 of 20 samples is the 19th fastest)."""
    ordered = sorted(values)
    rank = max(1, math.ceil(share * len(ordered)))
    return ordered[rank - 1]


def _samples() -> dict:
    from apps.performance.queries import pick_samples

    found = pick_samples()
    found["today"] = found["today"].isoformat()
    return found


def _measuring_user():
    from apps.access_control.models import Role
    from apps.access_control.services import assign_role
    from apps.identity.models import User

    user = User.objects.create_user(
        email="performance.measure@synthetic.test",
        display_name="Performance measurement (temporary)",
        password=None,
    )
    # Medical records for the patient screens (HIMS-DATA-003): search, records, restricted ones.
    for code in ("organization-administrator", "auditor", "medical-records-officer"):
        role = Role.objects.filter(code=code).first()
        if role is not None:
            assign_role(actor=None, user=user, role=role, reason="Response-time measurement")
    return user


def _client(user) -> Client:
    from apps.identity.mfa import SESSION_VERIFIED_KEY

    hosts = [h for h in settings.ALLOWED_HOSTS if h and "*" not in h and not h.startswith(".")]
    client = Client(HTTP_HOST=hosts[0] if hosts else "localhost")
    client.force_login(user)
    session = client.session
    session[SESSION_VERIFIED_KEY] = True  # as after two-factor sign-in
    session.save()
    return client


def _forget_requests(user) -> None:
    """Start each screen with a clean request count, so that the 40-odd screens measured in a
    row never reach the per-person limit (``HIMS_THROTTLE_USER``) the app sets for people."""
    cache.delete(f"throttle_user_{user.pk}")


def _measure_one(client: Client, endpoint: Endpoint, path: str, samples: int) -> dict:
    def call():
        with transaction.atomic():  # a failing call must not spoil the calls after it
            return client.get(path)

    for _ in range(WARM_UP):
        call()
    queries = 0

    def count(execute, sql, params, many, context):
        nonlocal queries
        if not sql.lstrip().upper().startswith(("SAVEPOINT", "RELEASE", "ROLLBACK")):
            queries += 1
        return execute(sql, params, many, context)

    with connection.execute_wrapper(count):
        response = call()
    timings = []
    for _ in range(samples):
        started = time.perf_counter()
        response = call()
        timings.append((time.perf_counter() - started) * 1000)
    p95 = percentile(timings, 0.95)
    result = {
        "key": endpoint.key,
        "label": endpoint.label,
        "area": area_of_path(path),
        "path": path.split("?")[0],
        "status": response.status_code,
        "samples": samples,
        "p50_ms": round(statistics.median(timings), 1),
        "p95_ms": round(p95, 1),
        "max_ms": round(max(timings), 1),
        "queries": queries,
        "target_ms": endpoint.target_ms,
        "passed": True,
        "detail": "",
    }
    if response.status_code != 200:
        result.update(passed=False, detail=f"Answered {response.status_code}, not 200.")
    elif p95 > endpoint.target_ms:
        result.update(
            passed=False,
            detail=f"p95 {p95:.0f} ms is over the {endpoint.target_ms:.0f} ms target.",
        )
    return result


def measure(*, samples: int = DEFAULT_SAMPLES, endpoints=None) -> list[dict]:
    """Measure every endpoint; nothing the measurement creates is kept (rolled back)."""
    samples = max(3, min(samples, MAX_SAMPLES))
    endpoints = all_endpoints() if endpoints is None else endpoints
    results = []
    with transaction.atomic():
        found = _samples()
        user = _measuring_user()
        client = _client(user)
        for endpoint in endpoints:
            path = endpoint.path(found)
            _forget_requests(user)
            try:
                results.append(_measure_one(client, endpoint, path, samples))
            except Exception as exc:  # one broken screen must not hide the others
                results.append(
                    {
                        "key": endpoint.key,
                        "label": endpoint.label,
                        "area": area_of_path(path),
                        "path": path.split("?")[0],
                        "status": 0,
                        "samples": 0,
                        "p50_ms": 0.0,
                        "p95_ms": 0.0,
                        "max_ms": 0.0,
                        "queries": 0,
                        "target_ms": endpoint.target_ms,
                        "passed": False,
                        "detail": f"Could not be measured: {type(exc).__name__}",
                    }
                )
        transaction.set_rollback(True)
    return results
