"""Fill a throw-away database with production-like synthetic records (spec 28.6, 31.1;
HIMS-DATA-002, HIMS-DATA-003).

Sized on a 500-bed hospital: about 2,000 staff, a year of Phase 1 use, the audit traffic
Phase 2 adds, and the patient register of several years with its contacts, ID numbers,
consents, people, earlier names, restricted records and emergency access
(docs/architecture/data-architecture/volume-check.md shows the arithmetic). ``scale``
multiplies every count (0.1 for a quick look, 10 for several years).

Every person and record is invented ("Synthetic Staff 000123", ``@synthetic.test``, patient
names made of syllables that belong to nobody). The command refuses any database except
``hims_volume`` (and test databases), so it can never add rows to a real hospital.

The big tables are filled with ``INSERT ... SELECT generate_series`` (seconds instead of
minutes). Columns a test does not name get their model default, so a new column with a default
needs no change here; a new required column without one makes the seeding test fail with its
name.
"""

import uuid
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.db import connection, transaction
from django.db.models import NOT_PROVIDED
from django.utils import timezone

from apps.organizations.dates import hospital_timezone, hospital_today
from common.environment import LOCAL_ENVIRONMENTS

VOLUME_DATABASE = "hims_volume"

# A 500-bed hospital (see volume-check.md). Shifts: one a day per person over ROTA_DAYS.
PROFILE = {
    "staff": 2_000,
    "wards": 50,  # 10 rooms of 3 beds each: 1,500 beds
    "departments": 30,
    # 2 million audit events in all: 1.5 million of the Phase 1 kinds and 500,000 patient
    # events (records opened, searches, histories), about six weeks of Phase 2 use.
    "audit_events": 1_500_000,
    "patient_audit_events": 500_000,
    "user_sessions": 300_000,
    "notifications": 300_000,
    "outbox_events": 500_000,
    "idempotency_records": 50_000,
    "issued_numbers": 300_000,
    "password_resets": 10_000,
    # About 150,000 new patients a year: a little over three years of registrations. Contacts,
    # ID numbers, consents, people and earlier names follow as shares of the patients.
    "patients": 500_000,
    "patient_emergency_access": 2_000,
}
# Shares of the patients (a mobile each, a family in five sharing one; addresses, ID numbers,
# SMS decisions, relatives and earlier names for some).
PATIENT_SHARES = {
    "addresses": 0.6,
    "identifiers": 0.6,
    "sms_consents": 0.3,
    "relationships": 0.2,
    "aliases": 0.02,
}
RESTRICTED_EVERY = 1_000  # one patient in a thousand has a restricted record
ROTA_DAYS = 60
# One in ten synthetic staff gets one of these administrative roles.
ADMIN_ROLES = (
    "hr-credentialing-officer",
    "facility-administrator",
)
BATCH = 250_000


class VolumeError(Exception):
    pass


def check_safe(database_name: str | None = None) -> None:
    name = database_name or connection.settings_dict["NAME"]
    if settings.HIMS_ENVIRONMENT not in LOCAL_ENVIRONMENTS:
        raise VolumeError(
            f"Refused: HIMS_ENVIRONMENT is '{settings.HIMS_ENVIRONMENT}', not local or test."
        )
    if name != VOLUME_DATABASE and not name.startswith("test_"):
        raise VolumeError(
            f"Refused: synthetic volume goes only into '{VOLUME_DATABASE}', not '{name}'."
        )


# Even a small run needs enough people and places for searches to be selective, as in a hospital.
MINIMUM = {"staff": 50, "wards": 5, "departments": 5, "patients": 200}


def counts_for(scale: float) -> dict[str, int]:
    return {key: max(MINIMUM.get(key, 1), int(value * scale)) for key, value in PROFILE.items()}


# --- Bulk SQL --------------------------------------------------------------------------------


def _default_sql(field):
    """SQL for a column the caller did not name, from the model's default."""
    default = field.default
    if default is NOT_PROVIDED:
        if field.null:
            return None
        if field.get_internal_type() in ("CharField", "TextField", "SlugField", "EmailField"):
            return "''"
        raise VolumeError(
            f"{field.model._meta.db_table}.{field.column} is required and has no default: "
            "add it to the synthetic volume (apps/performance/volume.py)."
        )
    if default is uuid.uuid4:
        return "gen_random_uuid()"
    if default is timezone.now:
        return "now()"
    if default is dict:
        return "'{}'::jsonb"
    if default is list:
        return "'[]'::jsonb"
    if isinstance(default, bool):
        return "true" if default else "false"
    if isinstance(default, int | float):
        return str(default)
    if isinstance(default, str):
        return "'" + default.replace("'", "''") + "'"
    if field.null:
        return None
    raise VolumeError(  # pragma: no cover - only for a new kind of default
        f"{field.model._meta.db_table}.{field.column}: unknown default {default!r}"
    )


def insert_series(model, count: int, columns: dict[str, str], params: dict | None = None) -> int:
    """Insert ``count`` rows; ``columns`` maps a column to an SQL expression of ``g`` (1..count)."""
    names, values = [], []
    for field in model._meta.concrete_fields:
        expression = columns.get(field.column)
        if expression is None:
            expression = _default_sql(field)
        if expression is None:
            continue
        names.append(f'"{field.column}"')
        values.append(expression)
    unknown = set(columns) - {f.column for f in model._meta.concrete_fields}
    if unknown:
        raise VolumeError(f"{model._meta.db_table} has no column(s) {sorted(unknown)}")
    # Table and column names come from the model and the expressions from this module; every
    # value is a query parameter.
    sql = (
        f'INSERT INTO "{model._meta.db_table}" ({", ".join(names)}) '  # noqa: S608
        f"SELECT {', '.join(values)} FROM generate_series(%(start)s, %(end)s) AS g"
    )
    done = 0
    while done < count:
        end = min(count, done + BATCH)
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql, {**(params or {}), "start": done + 1, "end": end})
        done = end
    return count


# --- Seeding ---------------------------------------------------------------------------------


def _structure(organization, n: dict, tag: str) -> dict:
    """A facility with departments, wards, rooms and beds; staff with accounts and access."""
    from apps.access_control.models import Role, RoleAssignment
    from apps.beds.models import Bed
    from apps.facilities.location_models import Building, Floor, Room, Ward
    from apps.facilities.models import Department, Facility
    from apps.identity.models import User
    from apps.rosters.models import ShiftType
    from apps.staff.models import StaffCredential, StaffMember

    org = {"organization": organization}
    facility = Facility.objects.create(
        **org,
        code=f"volume-{tag}",
        name="Synthetic Volume Hospital",
        facility_type="hospital",
        country=organization.country,
        state_region="Synthetic State",
        city="Synthetic City",
        address_line1="1 Synthetic Road",
        postal_code="000000",
        timezone=organization.default_timezone,
        phone="+10000000000",
    )
    place = {**org, "facility": facility}
    departments = Department.objects.bulk_create(
        Department(
            **place, code=f"dept-{i:03d}", name=f"Department {i:03d}", department_type="clinical"
        )
        for i in range(n["departments"])
    )
    building = Building.objects.create(**place, code="main", name="Main block")
    floors = Floor.objects.bulk_create(
        Floor(**place, building=building, level=level, name=f"Floor {level}") for level in range(5)
    )
    wards = Ward.objects.bulk_create(
        Ward(
            **place,
            floor=floors[i % len(floors)],
            department=departments[i % len(departments)],
            code=f"ward-{i:03d}",
            name=f"Ward {i:03d}",
            ward_type="icu" if i % 10 == 0 else "general",
        )
        for i in range(n["wards"])
    )
    rooms = Room.objects.bulk_create(
        Room(**place, ward=ward, code=f"r{r:02d}", name=f"Room {r:02d}", room_type="general")
        for ward in wards
        for r in range(10)
    )
    statuses = ("available", "occupied", "occupied", "cleaning", "available", "reserved")
    Bed.objects.bulk_create(
        Bed(
            **place,
            room=room,
            ward=room.ward,
            code=f"{room.code}-b{b}",
            bed_type="icu" if room.ward.ward_type == "icu" else "general",
            status=statuses[(i + b) % len(statuses)],
        )
        for i, room in enumerate(rooms)
        for b in range(3)
    )

    from django.contrib.auth.hashers import make_password

    NO_PASSWORD = make_password(None)
    first = User.objects.filter(
        email__startswith="staff", email__endswith="@synthetic.test"
    ).count()
    users = User.objects.bulk_create(
        User(
            email=f"staff{first + i:06d}@synthetic.test",
            display_name=f"Synthetic Staff {first + i:06d}",
            password=NO_PASSWORD,  # unusable: nobody can sign in as them
        )
        for i in range(n["staff"])
    )
    kinds = ("doctor", "nurse", "nurse", "nurse", "pharmacist", "lab_technician")
    staff = StaffMember.objects.bulk_create(
        StaffMember(
            **org,
            user=user,
            employee_number=f"V{first + i:06d}",
            given_name="Synthetic",
            family_name=f"Staff {i:06d}",
            staff_type=kinds[i % len(kinds)],
            joined_on=date(2020, 1, 1) + timedelta(days=i % 1500),
        )
        for i, user in enumerate(users)
    )
    today = hospital_today()
    licence = {"doctor": "medical_registration", "nurse": "nursing_registration"}
    StaffCredential.objects.bulk_create(
        StaffCredential(
            **org,
            staff=member,
            credential_type=licence.get(member.staff_type, "pharmacy_registration"),
            registration_number=f"SYN-{first + i:06d}",
            issuing_authority="Synthetic Council",
            jurisdiction="Synthetic State",
            expires_at=today + timedelta(days=(i * 7) % 1100 - 100),
        )
        for i, member in enumerate(staff)
    )
    roles = list(Role.objects.filter(code__in=ADMIN_ROLES))
    if roles:
        RoleAssignment.objects.bulk_create(
            RoleAssignment(
                **org,
                user=user,
                role=roles[i % len(roles)],
                facility=facility
                if roles[i % len(roles)].code == "facility-administrator"
                else None,
                reason="Synthetic volume",
            )
            for i, user in enumerate(users[: max(1, len(users) // 10)])
        )
    shift_type, _ = ShiftType.objects.get_or_create(
        code="volume-day",
        defaults={"name": "Synthetic day", "start_time": time(8), "end_time": time(16)},
    )
    return {
        "facility": facility,
        "departments": departments,
        "users": users,
        "staff": staff,
        "shift_type": shift_type,
    }


def _shifts(organization, built: dict) -> int:
    from apps.rosters.models import Shift

    zone = hospital_timezone()
    start = hospital_today() - timedelta(days=ROTA_DAYS // 2)
    departments = built["departments"]
    total = 0
    for day_offset in range(ROTA_DAYS):
        day = start + timedelta(days=day_offset)
        begins = datetime.combine(day, time(8), zone)
        Shift.objects.bulk_create(
            Shift(
                organization=organization,
                staff=member,
                facility=built["facility"],
                department=departments[i % len(departments)],
                shift_type=built["shift_type"],
                on_date=day,
                starts_at=begins,
                ends_at=begins + timedelta(hours=8),
            )
            for i, member in enumerate(built["staff"])
        )
        total += len(built["staff"])
    return total


ACTIONS = [
    "auth.login.succeeded",
    "auth.logout",
    "staff.member.updated",
    "staff.credential.verified",
    "rota.shift.added",
    "audit.searched",
    "bed.status.changed",
    "access.role_assignment.granted",
    "notification.retried",
    "organization.updated",
]
RESOURCES = ["user", "staff_member", "shift", "bed", "role_assignment", "audit_event"]


def _bulk(organization, built: dict, n: dict, tag: str) -> dict[str, int]:
    from apps.audit.models import AuditEvent
    from apps.identity.models import PasswordReset, UserSession
    from apps.notifications.models import Notification
    from apps.numbering.models import IssuedNumber, NumberingScheme
    from common.idempotency.models import IdempotencyRecord
    from common.outbox.models import OutboxEvent

    users = [str(u.pk) for u in built["users"]]
    common = {
        "users": users,
        "n_users": len(users),
        "org": str(organization.pk),
        "facility": str(built["facility"].pk),
        "actions": ACTIONS,
        "resources": RESOURCES,
        "tag": tag,  # keeps keys unique when the volume is added more than once
    }
    user = "(%(users)s::uuid[])[1 + (g %% %(n_users)s)]"
    year_ago = "now() - (((g::bigint * 7919) %% 31536000) * interval '1 second')"
    browser = "'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36'"
    with connection.cursor() as cursor:
        cursor.execute("SELECT setseed(0.42)")
    done = {}
    done["audit_events"] = insert_series(
        AuditEvent,
        n["audit_events"],
        {
            "occurred_at": year_ago,
            "organization_id": "%(org)s::uuid",
            "facility_id": "%(facility)s::uuid",
            "actor_type": "'user'",
            "actor_id": user,
            "action": "(%(actions)s::text[])[1 + (g %% 10)]",
            "resource_type": "(%(resources)s::text[])[1 + (g %% 6)]",
            "resource_id": "((g * 31) %% 200000)::text",
            "outcome": "CASE WHEN g %% 50 = 0 THEN 'denied' ELSE 'success' END",
            "request_id": "md5(g::text)",
            "ip_address": "('10.0.' || (g %% 250) || '.' || (g %% 200 + 1))::inet",
            "user_agent": browser,
        },
        common,
    )
    done["user_sessions"] = insert_series(
        UserSession,
        n["user_sessions"],
        {
            "user_id": user,
            "session_key": "substr(md5(%(tag)s || g::text) || md5(g::text), 1, 40)",
            "created_at": year_ago,
            "ip_address": "('10.1.' || (g %% 250) || '.1')::inet",
            "user_agent": browser,
            "ended_at": f"CASE WHEN g %% 50 = 0 THEN NULL ELSE {year_ago} + interval '8 hours' END",
            "end_reason": "CASE WHEN g %% 50 = 0 THEN '' WHEN g %% 3 = 0 THEN 'expired' "
            "ELSE 'logout' END",
        },
        common,
    )
    done["notifications"] = insert_series(
        Notification,
        n["notifications"],
        {
            "created_at": year_ago,
            "channel": "'email'",
            "category": "'staff'",
            "template": "'invitation'",
            "recipients": "jsonb_build_array('staff' || lpad((g %% 2000)::text, 6, '0') "
            "|| '@synthetic.test')",
            "subject": "'Synthetic message'",
            "status": "CASE g %% 100 WHEN 0 THEN 'failed' WHEN 1 THEN 'gave_up' "
            "WHEN 2 THEN 'skipped' ELSE 'sent' END",
            "attempts": "1",
            "next_attempt_at": f"CASE WHEN g %% 100 = 0 THEN {year_ago} END",
            "sent_at": f"CASE WHEN g %% 100 > 2 THEN {year_ago} END",
            "requested_by_id": user,
        },
        common,
    )
    recent = "now() - (((g::bigint * 7919) %% 3888000) * interval '1 second')"  # last 45 days
    done["outbox_events"] = insert_series(
        OutboxEvent,
        n["outbox_events"],
        {
            "event_type": "'staff.member.updated'",
            "occurred_at": recent,
            "customer_id": "'volume'",
            "aggregate_type": "'staff_member'",
            "aggregate_id": "(g %% 2000)::text",
            "correlation_id": "md5(g::text)",
            "status": "CASE WHEN g %% 1000 < 2 THEN 'pending' WHEN g %% 1000 < 5 THEN 'dead' "
            "WHEN g %% 1000 < 20 THEN 'dismissed' ELSE 'published' END",
            "attempts": "CASE WHEN g %% 1000 < 20 THEN 3 ELSE 1 END",
            "available_at": recent,
            "published_at": f"CASE WHEN g %% 1000 >= 20 THEN {recent} + interval '2 seconds' END",
            "resolved_at": f"CASE WHEN g %% 1000 BETWEEN 5 AND 19 THEN {recent} END",
        },
        common,
    )
    done["idempotency_records"] = insert_series(
        IdempotencyRecord,
        n["idempotency_records"],
        {
            "key": "md5(%(tag)s || 'key' || g::text)",
            "actor_id": user,
            "operation": "'staff.create'",
            "request_fingerprint": "md5(g::text)",
            "response_status": "201",
            # The hourly clean-up keeps about 49 hours of these (48 hours plus up to one hour).
            "created_at": "now() - (((g::bigint * 7919) %% 176400) * interval '1 second')",
            "expires_at": "now() - (((g::bigint * 7919) %% 176400) * interval '1 second') "
            "+ interval '48 hours'",
        },
        common,
    )
    numbers = 0
    for document_type, share in (("mrn", 0.6), ("encounter", 0.4)):
        scheme = (
            NumberingScheme.objects.filter(
                document_type=document_type, facility__isnull=True
            ).first()
            or NumberingScheme.objects.filter(document_type=document_type).first()
        )
        if scheme is None:
            continue
        numbers += insert_series(
            IssuedNumber,
            max(1, int(n["issued_numbers"] * share)),
            {
                "created_at": year_ago,
                "updated_at": year_ago,
                "organization_id": "%(org)s::uuid",
                "scheme_id": "%(scheme)s::uuid",
                "document_type": "%(doc)s",
                "value": "'VOL-' || %(tag)s || '-' || %(doc)s || '-' || lpad(g::text, 9, '0')",
                "sequence": "g",
            },
            {**common, "scheme": str(scheme.pk), "doc": document_type},
        )
    done["issued_numbers"] = numbers
    done["user_password_resets"] = insert_series(
        PasswordReset,
        n["password_resets"],
        {
            "user_id": user,
            "created_at": year_ago,
            "expires_at": f"{year_ago} + interval '1 hour'",
            "used_at": f"{year_ago} + interval '5 minutes'",
        },
        common,
    )
    return done


# --- Patients (HIMS-DATA-003) ----------------------------------------------------------------

# Invented names: two or three of these syllables. Nobody is called this, yet the names spell
# and sound like names, so similar-spelling and sound-alike search work as they do on real ones.
SYLLABLES = (
    "ka", "ri", "an", "de", "vi", "mo", "la", "su", "ne", "ta", "ja", "ro", "mi", "sha", "pa",
    "ku", "na", "lee", "ha", "ve", "di", "ya", "ma", "ni", "go", "ra", "sa", "bi", "te", "lo",
)  # fmt: skip
GIVEN_NAMES = 400
FAMILY_NAMES = 300


def invented_names(count: int, offset: int) -> list[str]:
    """``count`` different invented names, the same ones on every run."""
    names, seen, i = [], set(), 0
    while len(names) < count:
        k = i * 7919 + offset
        parts = []
        for _ in range(3 if i % 3 == 0 else 2):
            parts.append(SYLLABLES[k % len(SYLLABLES)])
            k //= len(SYLLABLES)
        word = "".join(parts)
        if word not in seen:
            seen.add(word)
            names.append(word)
        i += 1
    return names


def _patient_id(index: str) -> str:
    """The SQL id of synthetic patient number ``index`` (1..n): the same id from every table."""
    return f"md5(%(tag)s || 'p' || ({index})::text)::uuid"


def _patients(organization, built: dict, n: dict, tag: str) -> dict[str, int]:
    from apps.audit.models import AuditEvent
    from apps.audit.services import AuditAction
    from apps.patients import demographics
    from apps.patients.identifiers import kinds_for
    from apps.patients.models import (
        EmergencyAccess,
        Patient,
        PatientAlias,
        PatientConsent,
        PatientContact,
        PatientIdentifier,
        PatientRelationship,
    )

    given = invented_names(GIVEN_NAMES, 11)
    family = invented_names(FAMILY_NAMES, 977)
    total = n["patients"]
    india = organization.country == "IN"
    users = [str(u.pk) for u in built["users"]]
    params = {
        "tag": tag,
        "org": str(organization.pk),
        "facility": str(built["facility"].pk),
        "users": users,
        "n_users": len(users),
        "given": given,
        "family": family,
        "given_sounds": [demographics.sound_key(name) for name in given],
        "family_sounds": [demographics.sound_key(name) for name in family],
        "n_patients": total,
        "every": RESTRICTED_EVERY,
        "n_restricted": (total - 1) // RESTRICTED_EVERY + 1,
        # E.164 numbers in a range the generator alone uses (+91 90000 or +1 200 numbers).
        "phone_base": 919000000000 if india else 12000000000,
    }
    user = "(%(users)s::uuid[])[1 + (g %% %(n_users)s)]"
    owned = {"organization_id": "%(org)s::uuid"}
    years = "now() - (((g::bigint * 7919) %% 100000000) * interval '1 second')"  # ~3 years
    year_ago = "now() - (((g::bigint * 7919) %% 31536000) * interval '1 second')"
    # A few family names are very common (as Kumar, Singh or Devi are): the square of an even
    # spread puts about one patient in 17 under the commonest.
    spread = "(((g::bigint * 2654435761) %% 1000003) / 1000003.0)"
    family_at = f"1 + floor(%(n_family)s * {spread} * {spread})::int"
    given_at = "1 + ((g::bigint * 104729) %% %(n_given)s)::int"
    params.update(n_given=len(given), n_family=len(family))
    done = {}
    done["patients"] = insert_series(
        Patient,
        total,
        {
            **owned,
            "id": _patient_id("g"),
            "created_at": years,
            "updated_at": years,
            "mrn": "'MRN-' || upper(%(tag)s) || '-' || lpad(g::text, 8, '0')",
            "status": "'active'",
            "given_name": f"initcap((%(given)s::text[])[{given_at}])",
            "family_name": f"initcap((%(family)s::text[])[{family_at}])",
            "date_of_birth": "current_date - ((g::bigint * 7919) %% 32000)::int",
            "sex": "CASE WHEN g %% 2 = 0 THEN 'female' ELSE 'male' END",
            "is_restricted": "g %% %(every)s = 1",
            "restriction": "CASE WHEN g %% %(every)s = 1 THEN 'vip' ELSE '' END",
            "registered_facility_id": "%(facility)s::uuid",
            "registered_by_id": user,
            "search_name": f"(%(given)s::text[])[{given_at}] || ' ' || "
            f"(%(family)s::text[])[{family_at}]",
            "search_sounds": f"ARRAY[(%(given_sounds)s::text[])[{given_at}], "
            f"(%(family_sounds)s::text[])[{family_at}]]::varchar[]",
        },
        params,
    )
    # One mobile each; in one family in five, the next patient gives the same number.
    done["patient_contacts"] = insert_series(
        PatientContact,
        total,
        {
            **owned,
            "patient_id": _patient_id("g"),
            "created_at": years,
            "updated_at": years,
            "kind": "'mobile'",
            "phone": "'+' || (%(phone_base)s + CASE WHEN g %% 5 = 0 THEN g - 1 ELSE g END)",
            "is_primary": "true",
            "created_by_id": user,
        },
        params,
    )
    done["patient_contacts"] += insert_series(
        PatientContact,
        int(total * PATIENT_SHARES["addresses"]),
        {
            **owned,
            "patient_id": _patient_id("g"),
            "created_at": years,
            "updated_at": years,
            "kind": "'address'",
            "address_line1": "g || ' Synthetic Road'",
            "city": "'Synthetic City'",
            "state": "'Synthetic State'",
            "country": f"'{organization.country}'",
            "is_primary": "true",
        },
        params,
    )
    kind = "aadhaar" if "aadhaar" in kinds_for(organization.country) else "ssn"
    done["patient_identifiers"] = insert_series(
        PatientIdentifier,
        int(total * PATIENT_SHARES["identifiers"]),
        {
            **owned,
            "patient_id": _patient_id("g"),
            "created_at": years,
            "updated_at": years,
            "kind": f"'{kind}'",
            # Not a real ciphertext: the volume check never opens a number.
            "value_encrypted": "'synthetic-' || g",
            "value_hash": "encode(sha256((%(tag)s || 'id' || g)::bytea), 'hex')",
            "value_display": "'XXXX XXXX ' || lpad((g %% 10000)::text, 4, '0')",
        },
        params,
    )
    done["patient_consents"] = insert_series(
        PatientConsent,
        total,
        {
            **owned,
            "patient_id": _patient_id("g"),
            "created_at": years,
            "updated_at": years,
            "kind": "'privacy_notice'",
            "status": "'given'",
        },
        params,
    )
    done["patient_consents"] += insert_series(
        PatientConsent,
        int(total * PATIENT_SHARES["sms_consents"]),
        {
            **owned,
            "patient_id": _patient_id("g * 3"),
            "created_at": years,
            "updated_at": years,
            "kind": "'sms'",
            "status": "CASE WHEN g %% 4 = 0 THEN 'refused' ELSE 'given' END",
        },
        params,
    )
    done["patient_relationships"] = insert_series(
        PatientRelationship,
        int(total * PATIENT_SHARES["relationships"]),
        {
            **owned,
            "patient_id": _patient_id("g * 5"),
            "created_at": years,
            "updated_at": years,
            "relation": "(ARRAY['mother','spouse','emergency_contact','father'])[1 + g %% 4]",
            "name": "'Synthetic Relative ' || g",
            "is_emergency_contact": "g %% 4 = 2",
        },
        params,
    )
    done["patient_aliases"] = insert_series(
        PatientAlias,
        max(1, int(total * PATIENT_SHARES["aliases"])),
        {
            **owned,
            "patient_id": _patient_id("g * 50"),
            "created_at": years,
            "kind": "CASE WHEN g %% 5 = 0 THEN 'merged_mrn' ELSE 'previous_name' END",
            "given_name": "CASE WHEN g %% 5 = 0 THEN '' ELSE 'Synthetic' END",
            "family_name": "CASE WHEN g %% 5 = 0 THEN '' ELSE 'Earlier ' || g END",
            "mrn": "CASE WHEN g %% 5 = 0 THEN 'MRN-' || upper(%(tag)s) || '-OLD-' || g ELSE '' END",
        },
        params,
    )
    # Emergency access to the restricted records: nearly all reviewed, a few waiting.
    reviewed = "g %% 20 <> 0"
    done["patient_emergency_access"] = insert_series(
        EmergencyAccess,
        n["patient_emergency_access"],
        {
            **owned,
            "patient_id": _patient_id("1 + %(every)s * (g %% %(n_restricted)s)"),
            "created_at": year_ago,
            "updated_at": year_ago,
            "user_id": user,
            "reason": "'Synthetic emergency'",
            "expires_at": f"{year_ago} + interval '4 hours'",
            "reviewed_at": f"CASE WHEN {reviewed} THEN {year_ago} + interval '1 day' END",
            "reviewed_by_id": f"CASE WHEN {reviewed} THEN "
            "(%(users)s::uuid[])[1 + ((g + 1) %% %(n_users)s)] END",
            "outcome": f"CASE WHEN {reviewed} THEN 'appropriate' ELSE '' END",
        },
        params,
    )
    # What the patient screens add to the audit log: records opened (restricted ones marked, as
    # the app marks them), searches (no record) and histories.
    patient = "1 + ((g::bigint * 7919) %% %(n_patients)s)"
    viewed, searched, history = (
        AuditAction.PATIENT_RECORD_VIEWED,
        AuditAction.PATIENT_LIST_SEARCHED,
        AuditAction.PATIENT_HISTORY_VIEWED,
    )
    done["audit_events"] = insert_series(
        AuditEvent,
        n["patient_audit_events"],
        {
            "occurred_at": year_ago,
            "organization_id": "%(org)s::uuid",
            "facility_id": "%(facility)s::uuid",
            "actor_type": "'user'",
            "actor_id": user,
            "action": f"CASE WHEN g %% 10 < 7 THEN '{viewed}' WHEN g %% 10 < 9 "
            f"THEN '{searched}' ELSE '{history}' END",
            "resource_type": "'patient'",
            "resource_id": f"CASE WHEN g %% 10 IN (7, 8) THEN '' "
            f"ELSE ({_patient_id(patient)})::text END",
            "metadata": f"CASE WHEN g %% 10 < 7 AND ({patient}) %% %(every)s = 1 "
            'THEN \'{"restricted": true, "via": "restricted_permission"}\'::jsonb '
            "ELSE '{}'::jsonb END",
            "outcome": "'success'",
            "request_id": "md5('patient' || g::text)",
            "ip_address": "('10.2.' || (g %% 250) || '.' || (g %% 200 + 1))::inet",
        },
        params,
    )
    return done


MAIN_TABLES = (
    "patients",
    "patient_contacts",
    "patient_identifiers",
    "patient_consents",
    "patient_relationships",
    "patient_aliases",
    "patient_emergency_access",
    "audit_events",
    "user_sessions",
    "notifications",
    "outbox_events",
    "idempotency_records",
    "issued_numbers",
    "user_password_resets",
    "shifts",
    "staff_members",
    "staff_credentials",
    "role_assignments",
    "beds",
    "users",
)


def seed(*, scale: float = 1.0, progress=None) -> dict[str, int]:
    """Add the synthetic records; returns how many rows went into each table."""
    from apps.organizations.models import Organization

    check_safe()
    say = progress or (lambda message: None)
    organization = Organization.objects.first()
    if organization is None:
        raise VolumeError("Provision the organization first (provision_organization).")
    n = counts_for(scale)
    tag = uuid.uuid4().hex[:8]
    say(f"Hospital structure and {n['staff']:,} staff...")
    with transaction.atomic():
        built = _structure(organization, n, tag)
    say(f"Rota: {ROTA_DAYS} days of shifts...")
    with transaction.atomic():
        added = {"shifts": _shifts(organization, built)}
    say("Audit log, sign-ins, messages, background events, numbers...")
    added.update(_bulk(organization, built, n, tag))
    say(f"Patients: {n['patients']:,} with contacts, ID numbers, consents and people...")
    for table, rows in _patients(organization, built, n, tag).items():
        added[table] = added.get(table, 0) + rows
    added.update({"staff_members": n["staff"], "users": n["staff"], "beds": n["wards"] * 30})
    say("Updating PostgreSQL's statistics (ANALYZE)...")
    with connection.cursor() as cursor:
        # Every table, not only the filled ones: the busy queries also join small tables (roles,
        # permissions), and stale statistics there can change which index a plan starts from.
        cursor.execute("ANALYZE")
    return added
