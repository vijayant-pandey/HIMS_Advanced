"""Fill one demo hospital's database with synthetic records for everything built so far
(HIMS-QA-004).

Runs inside one demo deployment (its own database), after ``migrate`` and
``provision_organization``. Everything goes through the same services as the screens, so every
rule is checked and every change is in the audit log, as if a hospital administrator had typed it.

What one hospital gets (``small`` shrinks it for the automated test):

* hospital settings: letterhead, leave year, leave entitlements, clinical privileges catalog;
* 3 branches, each with 12 departments (services, opening hours, a head), 2 buildings, 7 floors,
  13 wards (general, ICU, HDU, NICU, PICU, emergency, maternity, day care, theatre, recovery…),
  rooms and about 180 beds, some under maintenance or blocked;
* about 40 staff per branch: doctors, nurses, pharmacists, laboratory, administration; postings,
  qualifications and licences (some verified, some expiring soon or expired);
* sign-in accounts with roles: branch administrators, heads of department, HR, nurses, bed
  managers, equipment officers;
* two weeks of rota, on-call, leave (waiting, approved, refused), minimum staffing;
* equipment with service history (some overdue, one under repair);
* a cover arrangement, an open access review and supplier support access requests;
* patients (HIMS-PAT-001): the invented patients of ``patients.py`` registered at their branch by
  its front desk, with MRNs, address, a parent for children, next of kin for some, a previous
  hospital's MRN for some, consents, and one unknown (unconscious) patient per branch.

Clinical records come with the later Phase 2 tickets. Every later ticket adds its own records
here (docs/testing/demo-hospitals.md).
"""

import random
from dataclasses import dataclass, field
from datetime import date, time, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.access_control import delegations, reviews, support
from apps.access_control.models import Role
from apps.access_control.services import assign_role
from apps.beds.models import Bed
from apps.beds.services import change_bed_status, create_beds_in_room
from apps.equipment.models import Equipment, EquipmentServiceRecord
from apps.equipment.services import change_status, create_equipment, record_service
from apps.facilities.location_models import Building, Floor, Room, Ward
from apps.facilities.location_services import create_location
from apps.facilities.models import Department, Facility
from apps.facilities.services import (
    create_department,
    create_department_service,
    create_facility,
    set_department_hours,
    update_department,
)
from apps.identity.accounts import active_administrators
from apps.identity.models import User
from apps.numbering.services import ensure_default_schemes
from apps.organizations.dates import hospital_today
from apps.organizations.models import Organization
from apps.organizations.services import update_organization
from apps.patients.demographics import years_between
from apps.patients.services import register_patient
from apps.rosters import balances, staffing
from apps.rosters.models import LeaveRequest, ShiftType
from apps.rosters.services import add_shifts, approve_leave, reject_leave, request_leave
from apps.staff.catalogs import create_catalog_item
from apps.staff.models import Designation, QualificationType, Specialty, StaffMember
from apps.staff.privileges import grant_privilege
from apps.staff.services import (
    add_credential,
    add_department_assignment,
    add_qualification,
    create_staff_member,
    verify_credential,
    verify_qualification,
)
from common.environment import LOCAL_ENVIRONMENTS

from .hospitals import Hospital
from .patients import DemoPatient, patients_for
from .people import NameMaker

SUPPLIER_EMAIL = "support@hims-supplier.demo.test"

STATE_CODES = {
    "Delhi": "IN-DL",
    "Uttar Pradesh": "IN-UP",
    "Haryana": "IN-HR",
    "Telangana": "IN-TG",
    "Maharashtra": "IN-MH",
    "Tamil Nadu": "IN-TN",
    "Illinois": "US-IL",
    "Massachusetts": "US-MA",
    "Arizona": "US-AZ",
    "California": "US-CA",
    "Kentucky": "US-KY",
}


@dataclass(frozen=True)
class Dept:
    code: str
    name: str
    us_name: str
    kind: str
    open_24_hours: bool
    specialty: str | None
    services: tuple[str, ...]
    surgical: bool = False


DEPARTMENTS = (
    Dept(
        "EMR",
        "Emergency",
        "Emergency",
        "clinical",
        True,
        "emergency-medicine",
        ("Triage", "Resuscitation", "Minor procedures"),
    ),
    Dept(
        "GMED",
        "General Medicine",
        "Internal Medicine",
        "clinical",
        False,
        "general-medicine",
        ("OPD consultation", "Health check-up"),
    ),
    Dept(
        "CARD",
        "Cardiology",
        "Cardiology",
        "clinical",
        False,
        "cardiology",
        ("ECG", "Echocardiography", "Treadmill test"),
    ),
    Dept(
        "ORTH",
        "Orthopaedics",
        "Orthopedics",
        "clinical",
        False,
        "orthopedics",
        ("Fracture clinic", "Joint replacement OPD"),
        surgical=True,
    ),
    Dept(
        "PAED",
        "Paediatrics",
        "Pediatrics",
        "clinical",
        False,
        "pediatrics",
        ("Well-baby clinic", "Vaccination"),
    ),
    Dept(
        "OBGY",
        "Obstetrics & Gynaecology",
        "OB/GYN",
        "clinical",
        False,
        "obstetrics-gynecology",
        ("Antenatal clinic", "Labour and delivery"),
        surgical=True,
    ),
    Dept(
        "GSUR",
        "General Surgery",
        "General Surgery",
        "clinical",
        False,
        "general-surgery",
        ("Surgical OPD", "Day-care surgery"),
        surgical=True,
    ),
    Dept(
        "ICU",
        "Critical Care",
        "Critical Care",
        "clinical",
        True,
        "critical-care",
        ("Intensive care", "Ventilation"),
    ),
    Dept(
        "RADI",
        "Radiology",
        "Radiology",
        "diagnostic",
        False,
        "radiology",
        ("X-ray", "Ultrasound", "CT scan"),
    ),
    Dept(
        "LAB",
        "Laboratory",
        "Laboratory",
        "diagnostic",
        True,
        "pathology",
        ("Blood tests", "Microbiology"),
    ),
    Dept(
        "PHAR",
        "Pharmacy",
        "Pharmacy",
        "pharmacy",
        True,
        None,
        ("Outpatient pharmacy", "Ward supply"),
    ),
    Dept(
        "ADMN",
        "Hospital Administration",
        "Administration",
        "administrative",
        False,
        None,
        ("Front office", "Medical records"),
    ),
)

# (code, name, ward type, department, gender, age group, rooms, beds per room, room type, bed type)
WARDS = (
    (
        "A",
        0,
        "ER",
        "Emergency",
        "emergency",
        "EMR",
        "any",
        "any",
        1,
        10,
        "general",
        "emergency_trolley",
    ),
    (
        "A",
        1,
        "GWM",
        "General Ward (Men)",
        "general",
        "GMED",
        "male",
        "adult",
        4,
        6,
        "general",
        "general",
    ),
    (
        "A",
        1,
        "GWF",
        "General Ward (Women)",
        "general",
        "GMED",
        "female",
        "adult",
        4,
        6,
        "general",
        "general",
    ),
    ("A", 2, "ICU", "Intensive Care Unit", "icu", "ICU", "any", "adult", 8, 1, "icu_bay", "icu"),
    ("A", 2, "HDU", "High Dependency Unit", "hdu", "ICU", "any", "adult", 3, 2, "icu_bay", "hdu"),
    ("A", 3, "SUR", "Surgical Ward", "general", "GSUR", "any", "adult", 4, 6, "general", "general"),
    ("A", 3, "PVT", "Private Rooms", "private", "GMED", "any", "adult", 8, 1, "private", "private"),
    (
        "A",
        3,
        "OT",
        "Operating Theatres",
        "operating_theatre",
        "GSUR",
        "any",
        "any",
        3,
        1,
        "operating_room",
        "recovery",
    ),
    (
        "A",
        3,
        "REC",
        "Recovery (PACU)",
        "recovery",
        "GSUR",
        "any",
        "any",
        1,
        6,
        "recovery",
        "recovery",
    ),
    ("B", 0, "DAY", "Day Care", "day_care", "GSUR", "any", "any", 2, 6, "general", "day_care"),
    (
        "B",
        1,
        "MAT",
        "Maternity and Labour",
        "maternity",
        "OBGY",
        "female",
        "adult",
        4,
        4,
        "general",
        "labour",
    ),
    ("B", 1, "NICU", "Neonatal ICU", "nicu", "PAED", "any", "neonatal", 1, 8, "icu_bay", "nicu"),
    (
        "B",
        2,
        "PED",
        "Children's Ward",
        "general",
        "PAED",
        "any",
        "pediatric",
        4,
        6,
        "general",
        "general",
    ),
    ("B", 2, "PICU", "Paediatric ICU", "picu", "PAED", "any", "pediatric", 1, 6, "icu_bay", "picu"),
)
BUILDINGS = {"A": ("Main Block", (0, 1, 2, 3)), "B": ("Women and Child Block", (0, 1, 2))}
FLOOR_NAMES = {0: "Ground floor", 1: "First floor", 2: "Second floor", 3: "Third floor"}

EQUIPMENT = (
    ("Ventilator", "life_support", "ICU", "ICU", "Breathwell", "VX-500"),
    ("Ventilator", "life_support", "ICU", "ICU", "Breathwell", "VX-500"),
    ("Defibrillator", "life_support", "EMR", "ER", "CardioSafe", "D-20"),
    ("Patient monitor", "monitoring", "ICU", "ICU", "VitalView", "PM-12"),
    ("Patient monitor", "monitoring", "ICU", "HDU", "VitalView", "PM-12"),
    ("Infusion pump", "infusion", "GMED", "GWM", "FlowRight", "IP-3"),
    ("Syringe pump", "infusion", "PAED", "NICU", "FlowRight", "SP-1"),
    ("Neonatal incubator", "life_support", "PAED", "NICU", "Cradle Care", "NI-7"),
    ("Digital X-ray", "imaging", "RADI", None, "ClearRay", "DX-900"),
    ("Ultrasound scanner", "imaging", "RADI", None, "SonoPoint", "US-40"),
    ("Haematology analyser", "laboratory", "LAB", None, "LabCount", "HA-5"),
    ("Autoclave", "sterilization", "GSUR", "OT", "SteriMax", "AC-200"),
    ("Anaesthesia workstation", "surgical", "GSUR", "OT", "AeroGas", "AW-3"),
    ("Oxygen concentrator", "oxygen", "GMED", "GWF", "PureAir", "OC-10"),
    ("Wheelchair", "mobility", "EMR", "ER", "EasyRoll", "WC-1"),
)

PRIVILEGES = (
    ("Central line insertion", "Placing a central venous catheter."),
    ("Conscious sedation", "Giving procedural sedation outside theatre."),
    ("Mechanical ventilation", "Starting and managing a ventilator."),
    ("Coronary angiography", "Diagnostic coronary angiography in the cath lab."),
    ("Caesarean section", "Lower-segment caesarean section as primary surgeon."),
    ("Fracture reduction", "Closed reduction of fractures."),
    ("Laparoscopic surgery", "Laparoscopic abdominal surgery as primary surgeon."),
    ("Ultrasound reporting", "Signing ultrasound reports."),
)
PRIVILEGES_BY_DEPT = {
    "ICU": ("Central line insertion", "Mechanical ventilation", "Conscious sedation"),
    "EMR": ("Conscious sedation", "Central line insertion"),
    "CARD": ("Coronary angiography",),
    "OBGY": ("Caesarean section",),
    "ORTH": ("Fracture reduction", "Conscious sedation"),
    "GSUR": ("Laparoscopic surgery",),
    "RADI": ("Ultrasound reporting",),
}


class DemoError(Exception):
    pass


def check_safe() -> None:
    """Only demo deployments on a developer PC: never a real hospital's database."""
    if settings.HIMS_ENVIRONMENT not in LOCAL_ENVIRONMENTS:
        raise DemoError(f"Refused: HIMS_ENVIRONMENT is '{settings.HIMS_ENVIRONMENT}'.")
    deployment = settings.HIMS_DEPLOYMENT_ID
    if not (deployment.startswith("demo-") or deployment.startswith("test")):
        raise DemoError(
            f"Refused: demo records go only into demo deployments (demo-...), not '{deployment}'."
        )


@dataclass
class Context:
    hospital: Hospital
    organization: Organization
    admin: User
    password: str | None
    small: bool
    names: NameMaker
    random: random.Random
    today: date
    employee_numbers: int = 0
    registrations: int = 0
    counts: dict = field(default_factory=dict)
    logins: list = field(default_factory=list)
    desks: dict = field(default_factory=dict)  # facility id -> front desk account

    @property
    def country(self) -> str:
        return self.organization.country

    @property
    def domain(self) -> str:
        return f"{self.hospital.key}.demo.test"

    def add(self, what: str, n: int = 1) -> None:
        self.counts[what] = self.counts.get(what, 0) + n


def _designation(ctx: Context, code_in: str, code_us: str) -> Designation:
    return Designation.objects.get(code=code_in if ctx.country == "IN" else code_us)


def _qualification(code: str) -> QualificationType:
    return QualificationType.objects.get(code=code)


def _login(ctx: Context, user: User, what: str) -> None:
    if ctx.password:
        user.set_password(ctx.password)
        user.password_changed_at = timezone.now()
        user.save(update_fields=["password", "password_changed_at"])
    ctx.logins.append((user.email, what))


# --- Hospital-wide settings --------------------------------------------------------------------


def _hospital_settings(ctx: Context) -> None:
    org = ctx.organization
    first = ctx.hospital.branches[0]
    update_organization(
        actor=ctx.admin,
        organization_id=org.pk,
        version=org.version,
        letterhead_address=f"{first['address']}, {first['city']}, {first['state']} "
        f"{first['postal_code']}",
        letterhead_phone="+91 11 4000 0000" if ctx.country == "IN" else "+1 555 010 0000",
        letterhead_email=f"contact@{ctx.domain}",
        letterhead_website=f"https://{ctx.hospital.key}.demo.test",
        letterhead_registration="Synthetic demo hospital: not a real registration",
        letterhead_footer="Demo data only. Not a real hospital.",
        leave_year_start_month=4 if ctx.country == "IN" else 1,
    )
    year = balances.current_year()
    for leave_type, days, carry in (
        ("annual", 18 if ctx.country == "IN" else 15, 6),
        ("casual", 12 if ctx.country == "IN" else 0, 0),
        ("sick", 10 if ctx.country == "IN" else 8, 0),
    ):
        if days:
            balances.create_entitlement(
                actor=ctx.admin,
                leave_type=leave_type,
                from_year=year,
                days=days,
                max_carry_over=carry,
            )
    for name, description in PRIVILEGES:
        create_catalog_item(
            "clinical_privilege", actor=ctx.admin, name=name, description=description
        )
    ctx.add("clinical privileges", len(PRIVILEGES))


# --- One branch ---------------------------------------------------------------------------------


def _branch(ctx: Context, branch: dict) -> Facility:
    facility = create_facility(
        actor=ctx.admin,
        code=branch["code"],
        name=branch["name"],
        facility_type=Facility.FacilityType.HOSPITAL,
        country=ctx.country,
        state_region=branch["state"],
        city=branch["city"],
        address_line1=branch["address"],
        address_line2="",
        postal_code=branch["postal_code"],
        timezone=ctx.organization.default_timezone,
        phone="+91 11 4000 0000" if ctx.country == "IN" else "+1 555 010 0000",
    )
    ctx.add("branches")
    return facility


def _departments(ctx: Context, facility: Facility) -> dict[str, Department]:
    found = {}
    weekdays = [{"weekday": day, "opens_at": time(9), "closes_at": time(17)} for day in range(6)]
    for dept in DEPARTMENTS[: 6 if ctx.small else None]:
        department = create_department(
            actor=ctx.admin,
            facility=facility,
            code=dept.code,
            name=dept.name if ctx.country == "IN" else dept.us_name,
            department_type=dept.kind,
        )
        set_department_hours(
            actor=ctx.admin,
            department_id=department.pk,
            version=department.version,
            open_24_hours=dept.open_24_hours,
            sessions=[] if dept.open_24_hours else weekdays,
        )
        for service in dept.services:
            create_department_service(actor=ctx.admin, department=department, name=service)
        found[dept.code] = Department.objects.get(pk=department.pk)
        ctx.add("departments")
    return found


def _locations(ctx: Context, facility: Facility, departments: dict) -> dict[str, Ward]:
    floors = {}
    for code, (name, levels) in BUILDINGS.items():
        building = create_location(
            Building, actor=ctx.admin, facility=facility, code=code, name=name
        )
        ctx.add("buildings")
        for level in levels:
            floors[(code, level)] = create_location(
                Floor, actor=ctx.admin, building=building, level=level, name=FLOOR_NAMES[level]
            )
            ctx.add("floors")
    wards = {}
    for (
        building,
        level,
        code,
        name,
        ward_type,
        dept,
        gender,
        age,
        rooms,
        per_room,
        room_type,
        bed_type,
    ) in WARDS:
        if dept not in departments:
            continue
        ward = create_location(
            Ward,
            actor=ctx.admin,
            floor=floors[(building, level)],
            department=departments[dept],
            code=code,
            name=name,
            ward_type=ward_type,
            gender_restriction=gender,
            age_group=age,
        )
        wards[code] = ward
        ctx.add("wards")
        for number in range(1, (min(rooms, 2) if ctx.small else rooms) + 1):
            room_code = f"{level}{number:02d}" if rooms > 1 else f"{level}00"
            room = create_location(
                Room,
                actor=ctx.admin,
                ward=ward,
                code=room_code,
                name=f"{name} room {room_code}" if rooms > 1 else name,
                room_type=room_type,
                is_isolation_capable=ward_type in ("icu", "picu", "nicu") and number == 1,
            )
            ctx.add("rooms")
            beds = create_beds_in_room(
                actor=ctx.admin,
                room=room,
                prefix=f"{code}{room_code}-B",
                start=1,
                count=min(per_room, 3) if ctx.small else per_room,
                bed_type=bed_type,
            )
            ctx.add("beds", len(beds))
    # A few beds out of use, with reasons, so the Bed board shows every colour.
    beds = list(Bed.objects.filter(facility=facility).order_by("code"))
    reasons = (
        (Bed.Status.MAINTENANCE, "Broken side rail: biomedical team informed"),
        (Bed.Status.BLOCKED, "Kept free for an expected transfer"),
        (Bed.Status.MAINTENANCE, "Mattress replacement"),
        (Bed.Status.OUT_OF_SERVICE, "Room being repainted"),
    )
    for index, bed in enumerate(beds[5 :: max(1, len(beds) // 8)][: len(reasons)]):
        status, reason = reasons[index]
        change_bed_status(
            actor=ctx.admin, bed_id=bed.pk, version=bed.version, status=status, reason=reason
        )
        ctx.add("beds out of use")
    return wards


# --- Staff ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Job:
    staff_type: str
    designation: tuple[str, str]  # (India, US)
    qualifications: tuple[tuple[str, str], ...]  # ((India, US), ...)
    credential: tuple[str, str] | None  # (India type, US type)
    sex: str | None = None


CONSULTANT = Job(
    "doctor",
    ("in-consultant", "us-attending-physician"),
    (("in-mbbs", "us-md"), ("in-md", "us-board-certification")),
    ("medical_registration", "state_license"),
)
SURGEON = Job(
    "doctor",
    ("in-senior-consultant", "us-attending-physician"),
    (("in-mbbs", "us-md"), ("in-ms", "us-board-certification")),
    ("medical_registration", "state_license"),
)
RESIDENT = Job(
    "doctor",
    ("in-junior-resident", "us-resident"),
    (("in-mbbs", "us-md"),),
    ("medical_registration", "state_license"),
)
NURSE = Job(
    "nurse",
    ("in-staff-nurse", "us-registered-nurse"),
    (("in-bsc-nursing", "us-bsn"),),
    ("nursing_registration", "state_license"),
)
CHARGE_NURSE = Job(
    "nurse",
    ("in-ward-sister", "us-charge-nurse"),
    (("in-gnm", "us-bsn"),),
    ("nursing_registration", "state_license"),
)
PHARMACIST = Job(
    "pharmacist",
    ("pharmacist", "pharmacist"),
    (("in-bpharm", "us-pharmd"),),
    ("pharmacy_registration", "state_license"),
)
LAB_TECH = Job(
    "lab_technician", ("lab-technician", "lab-technician"), (("in-dmlt", "us-ascp-mls"),), None
)
RADIOLOGIST = Job(
    "radiologist",
    ("in-consultant", "us-attending-physician"),
    (("in-mbbs", "us-md"), ("in-md", "us-board-certification")),
    ("medical_registration", "state_license"),
)
ADMIN_OFFICER = Job("administrator", ("hospital-administrator", "hospital-administrator"), (), None)
FRONT_OFFICE = Job("administrator", ("front-office-executive", "front-office-executive"), (), None)
HR_OFFICER = Job("administrator", ("hr-executive", "hr-executive"), (), None)
WARD_CLERK = Job("administrator", ("in-medical-records-officer", "us-him-technician"), (), None)
BIOMEDICAL = Job("support", ("biomedical-engineer", "biomedical-engineer"), (), None)
DIETITIAN = Job("dietitian", ("dietitian", "dietitian"), (), None)

TEAM = {
    "EMR": (CONSULTANT, RESIDENT, CHARGE_NURSE, NURSE, NURSE, NURSE),
    "GMED": (CONSULTANT, RESIDENT, CHARGE_NURSE, NURSE, NURSE),
    "CARD": (CONSULTANT, RESIDENT, NURSE),
    "ORTH": (SURGEON, RESIDENT, NURSE),
    "PAED": (CONSULTANT, RESIDENT, NURSE, NURSE),
    "OBGY": (SURGEON, RESIDENT, NURSE, NURSE),
    "GSUR": (SURGEON, RESIDENT, NURSE),
    "ICU": (CONSULTANT, RESIDENT, CHARGE_NURSE, NURSE, NURSE, NURSE),
    "RADI": (RADIOLOGIST, LAB_TECH),
    "LAB": (CONSULTANT, LAB_TECH, LAB_TECH),
    "PHAR": (PHARMACIST, PHARMACIST),
    "ADMN": (ADMIN_OFFICER, FRONT_OFFICE, WARD_CLERK, BIOMEDICAL, DIETITIAN),
}


def _issuer(ctx: Context, kind: str, state: str) -> str:
    if ctx.country == "IN":
        return {
            "medical_registration": f"{state} Medical Council",
            "nursing_registration": f"{state} Nursing Council",
            "pharmacy_registration": f"{state} Pharmacy Council",
        }[kind]
    board = {
        "doctor": "Medical Board",
        "nurse": "Board of Nursing",
        "pharmacist": "Board of Pharmacy",
    }
    return f"{state} {board.get(kind, 'Licensing Board')}"


def _new_staff(
    ctx: Context, job: Job, department: Department, specialty_code: str | None, branch: dict
) -> StaffMember:
    given, family, _sex = ctx.names.person(job.sex)
    ctx.employee_numbers += 1
    joined = ctx.today - timedelta(days=ctx.random.randint(120, 3650))
    staff = create_staff_member(
        actor=ctx.admin,
        employee_number=f"{ctx.hospital.key[3:6].upper()}-{ctx.employee_numbers:05d}",
        given_name=given,
        family_name=family,
        staff_type=job.staff_type,
        joined_on=joined,
    )
    specialty = (
        Specialty.objects.get(code=specialty_code)
        if specialty_code and job.staff_type in ("doctor", "radiologist")
        else None
    )
    add_department_assignment(
        actor=ctx.admin,
        staff=staff,
        department=department,
        designation=_designation(ctx, *job.designation),
        specialty=specialty,
        is_primary=True,
        valid_from=joined,
    )
    for n, (code_in, code_us) in enumerate(job.qualifications):
        qualification = add_qualification(
            actor=ctx.admin,
            staff=staff,
            qualification_type=_qualification(code_in if ctx.country == "IN" else code_us),
            specialty=specialty if n > 0 else None,
            institution=f"Demo College of Medicine, {branch['city']}",
            year_awarded=joined.year - 2 - (len(job.qualifications) - n) * 3,
        )
        if ctx.employee_numbers % 3:  # two in three checked by HR
            verify_qualification(
                actor=ctx.admin, staff=staff, qualification_id=qualification.pk, verified=True
            )
    if job.credential:
        kind = job.credential[0 if ctx.country == "IN" else 1]
        ctx.registrations += 1
        # Spread the expiry dates: some expired, some due in 7/30/60 days, most far away.
        offset = (-12, 5, 25, 55, 400, 700, 900)[ctx.registrations % 7]
        credential = add_credential(
            actor=ctx.admin,
            staff=staff,
            credential_type=kind,
            registration_number=f"DEMO-{ctx.hospital.key[:2].upper()}-{ctx.registrations:06d}",
            issuing_authority=_issuer(
                ctx, kind if ctx.country == "IN" else job.staff_type, branch["state"]
            ),
            jurisdiction=STATE_CODES.get(branch["state"], ctx.country),
            valid_from=joined,
            expires_at=ctx.today + timedelta(days=offset),
        )
        if offset > 0:
            verify_credential(actor=ctx.admin, credential_id=credential.pk, verified=True)
    ctx.add("staff")
    return staff


def _account(ctx: Context, staff: StaffMember, local_part: str, what: str) -> User:
    user = User.objects.create_user(
        email=f"{local_part}@{ctx.domain}", display_name=f"{staff.given_name} {staff.family_name}"
    )
    staff.user = user
    staff.save(update_fields=["user"])
    _login(ctx, user, what)
    return user


def _staff(ctx: Context, facility: Facility, departments: dict, branch: dict) -> dict:
    team: dict[str, list[StaffMember]] = {}
    for dept in DEPARTMENTS:
        department = departments.get(dept.code)
        if department is None:
            continue
        jobs = TEAM[dept.code][: 3 if ctx.small else None]
        team[dept.code] = [_new_staff(ctx, job, department, dept.specialty, branch) for job in jobs]
        # The first person heads the department.
        head = team[dept.code][0]
        update_department(
            actor=ctx.admin, department_id=department.pk, version=department.version, head=head
        )
    roles = {role.code: role for role in Role.objects.filter(is_system=True)}
    code = facility.code.lower()
    admin_staff = team.get("ADMN", team["EMR"])[0]
    user = _account(ctx, admin_staff, f"admin.{code}", f"{facility.name}: branch administrator")
    assign_role(
        actor=None,
        user=user,
        role=roles["facility-administrator"],
        facility=facility,
        reason="Demo: branch administrator",
    )
    cardiology = departments.get("CARD") or departments["EMR"]
    hod = team.get("CARD", team["EMR"])[0]
    user = _account(ctx, hod, f"hod.{code}", f"{facility.name}: head of {cardiology.name}")
    assign_role(
        actor=None,
        user=user,
        role=roles["department-head"],
        facility=facility,
        department=cardiology,
        reason="Demo: head of department",
    )
    nurse = team.get("ICU", team["EMR"])[-1]
    user = _account(ctx, nurse, f"nurse.{code}", f"{facility.name}: nurse (basic access)")
    assign_role(
        actor=None,
        user=user,
        role=roles["basic-staff"],
        facility=facility,
        reason="Demo: basic staff access",
    )
    if "ADMN" in team and len(team["ADMN"]) >= 4:
        clerk, engineer = team["ADMN"][2], team["ADMN"][3]
        user = _account(ctx, clerk, f"beds.{code}", f"{facility.name}: bed manager")
        assign_role(
            actor=None,
            user=user,
            role=roles["bed-manager"],
            facility=facility,
            reason="Demo: bed manager",
        )
        user = _account(ctx, engineer, f"equipment.{code}", f"{facility.name}: equipment officer")
        assign_role(
            actor=None,
            user=user,
            role=roles["equipment-officer"],
            facility=facility,
            reason="Demo: equipment officer",
        )
    # The front office executive registers this branch's patients (HIMS-PAT-001).
    desk = team["ADMN"][1] if len(team.get("ADMN", [])) >= 2 else team["EMR"][1]
    user = _account(ctx, desk, f"frontdesk.{code}", f"{facility.name}: front desk (patients)")
    assign_role(
        actor=None,
        user=user,
        role=roles["receptionist"],
        facility=facility,
        reason="Demo: front desk",
    )
    ctx.desks[facility.pk] = user
    return team


def _privileges(ctx: Context, team: dict, departments: dict) -> None:
    from apps.staff.models import ClinicalPrivilege

    catalog = {p.name: p for p in ClinicalPrivilege.objects.all()}
    for dept_code, names in PRIVILEGES_BY_DEPT.items():
        if dept_code not in team:
            continue
        doctor = team[dept_code][0]
        for name in names:
            grant_privilege(
                actor=ctx.admin,
                staff=doctor,
                privilege=catalog[name],
                department=departments[dept_code],
                valid_until=ctx.today + timedelta(days=365),
                note="Demo: granted after supervised cases",
            )
            ctx.add("privileges given")


# --- Rota, leave and minimum staffing ---------------------------------------------------------


def _rota(ctx: Context, team: dict, departments: dict) -> None:
    shift_types = {s.code: s for s in ShiftType.objects.all()}
    first, last = ctx.today, ctx.today + timedelta(days=6 if ctx.small else 13)
    for dept_code, people in team.items():
        department = departments[dept_code]
        nurses = [p for p in people if p.staff_type == "nurse"]
        doctors = [p for p in people if p.staff_type in ("doctor", "radiologist")]
        others = [p for p in people if p not in nurses and p not in doctors]
        cycle = ("morning", "evening", "night")
        for n, nurse in enumerate(nurses):
            created, _ = add_shifts(
                actor=ctx.admin,
                staff=nurse,
                department=department,
                shift_type=shift_types[cycle[n % 3]],
                from_date=first,
                to_date=last,
                weekdays=[d for d in range(7) if d != (n + 2) % 7],
            )
            ctx.add("shifts", len(created))
        for n, doctor in enumerate(doctors):
            created, _ = add_shifts(
                actor=ctx.admin,
                staff=doctor,
                department=department,
                shift_type=shift_types["general"],
                from_date=first,
                to_date=last,
                weekdays=[0, 1, 2, 3, 4] if n == 0 else [0, 2, 4, 5],
            )
            ctx.add("shifts", len(created))
            if n == 1:  # the junior doctor is on call on two nights
                created, _ = add_shifts(
                    actor=ctx.admin,
                    staff=doctor,
                    department=department,
                    shift_type=shift_types["on-call-night"],
                    from_date=first,
                    to_date=last,
                    weekdays=[1, 3],
                )
                ctx.add("on-call", len(created))
        for person in others:
            created, _ = add_shifts(
                actor=ctx.admin,
                staff=person,
                department=department,
                shift_type=shift_types["general"],
                from_date=first,
                to_date=last,
                weekdays=[0, 1, 2, 3, 4],
            )
            ctx.add("shifts", len(created))
    for dept_code, minimum, shift in (
        ("ICU", 3, "morning"),
        ("ICU", 2, "night"),
        ("EMR", 2, "morning"),
    ):
        if dept_code in departments:
            staffing.create_requirement(
                actor=ctx.admin,
                department=departments[dept_code],
                shift_type=shift_types[shift],
                minimum=minimum,
                staff_type="nurse",
            )
            ctx.add("minimum staffing rules")


def _leave(ctx: Context, team: dict, departments: dict) -> None:
    people = [(code, p) for code, staff in team.items() for p in staff[1:]]
    if len(people) < 3:
        return
    plans = (
        ("annual", 20, 24, "approve", "Family wedding"),
        ("casual", 30, 30, None, "Personal work"),
        ("study", 40, 42, "reject", "Conference"),
    )
    for (dept_code, person), (leave_type, start, end, decision, reason) in zip(
        people[:: max(1, len(people) // 3)], plans, strict=False
    ):
        if ctx.country == "US" and leave_type == "casual":
            leave_type = "annual"
        leave = request_leave(
            actor=ctx.admin,
            staff=person,
            department=departments[dept_code],
            leave_type=leave_type,
            start_date=ctx.today + timedelta(days=start),
            end_date=ctx.today + timedelta(days=end),
            reason=reason,
        )
        if decision == "approve":
            approve_leave(
                actor=ctx.admin,
                leave_id=leave.pk,
                version=leave.version,
                note="Enjoy",
                cancel_shifts=True,
                allow_over_balance=True,
            )
        elif decision == "reject":
            reject_leave(
                actor=ctx.admin,
                leave_id=leave.pk,
                version=leave.version,
                note="Two others are away that week",
            )
        ctx.add("leave requests")
    ctx.counts["leave waiting"] = LeaveRequest.objects.filter(status="requested").count()


# --- Equipment ------------------------------------------------------------------------------------


def _equipment(ctx: Context, facility: Facility, departments: dict, wards: dict) -> None:
    for n, (name, category, dept_code, ward_code, maker, model) in enumerate(
        EQUIPMENT[: 5 if ctx.small else None], start=1
    ):
        if dept_code not in departments:
            continue
        bought = ctx.today - timedelta(days=300 + 60 * n)
        last = ctx.today - timedelta(days=(30 * n) % 330 + 20)
        # Every fourth item is overdue for its service, the rest are due later.
        next_due = (
            ctx.today - timedelta(days=5) if n % 4 == 0 else ctx.today + timedelta(days=15 * n)
        )
        item = create_equipment(
            actor=ctx.admin,
            organization=ctx.organization,
            facility=facility,
            asset_tag=f"{facility.code}-EQ-{n:03d}",
            name=name,
            category=category,
            department=departments[dept_code],
            ward=wards.get(ward_code) if ward_code else None,
            manufacturer=f"{maker} (demo)",
            model_name=model,
            serial_number=f"SN-DEMO-{facility.code}-{n:04d}",
            purchased_on=bought,
            warranty_until=bought + timedelta(days=730),
            last_service_on=last,
            next_service_due=next_due,
        )
        record_service(
            actor=ctx.admin,
            record=EquipmentServiceRecord(
                equipment=item,
                kind=EquipmentServiceRecord.Kind.SERVICE,
                performed_on=last,
                performed_by="Demo Biomedical Services",
                notes="Routine preventive maintenance",
                next_due=next_due if next_due > last else last + timedelta(days=180),
            ),
        )
        if n == 3:
            item.refresh_from_db()
            change_status(
                actor=ctx.admin,
                equipment_id=item.pk,
                version=item.version,
                status=Equipment.Status.MAINTENANCE,
                reason="Battery fault: sent for repair",
            )
        ctx.add("equipment")


# --- Access: cover, review, supplier support ------------------------------------------------------


def _demo_phone(ctx: Context, pick: random.Random) -> str:
    if ctx.country == "IN":
        return f"+91 90000 {pick.randint(10000, 99999)}"
    return f"+1 312 555 01{pick.randint(0, 99):02d}"  # 555-0100..0199: fictional


def _patients(ctx: Context, facility: Facility, branch: dict, invented: list[DemoPatient]) -> None:
    """Register the branch's invented patients through the registration service, as its front
    desk would (MRN issued, audited). No real identifiers: only an invented old-clinic MRN."""
    desk = ctx.desks[facility.pk]
    relatives = NameMaker(ctx.country, f"{ctx.hospital.key}-relatives-{branch['code']}")
    pick = random.Random(f"{ctx.hospital.key}-{branch['code']}-patients")  # noqa: S311 - demo data
    street = "Demo Colony" if ctx.country == "IN" else "Demo Street"
    for n, person in enumerate(invented):
        relationships = []
        if years_between(person.date_of_birth, ctx.today) < 18:
            given, _family, sex = relatives.person()
            relationships.append(
                {
                    "relation": "mother" if sex == "female" else "father",
                    "name": f"{given} {person.family_name}",
                    "phone": person.phone,
                    "is_legal_guardian": True,
                    "is_emergency_contact": True,
                }
            )
        elif n % 4 == 0:
            given, family, _sex = relatives.person()
            relationships.append(
                {
                    "relation": "next_of_kin",
                    "name": f"{given} {family}",
                    "phone": _demo_phone(ctx, pick),
                    "is_emergency_contact": True,
                }
            )
        old_mrn = {
            "kind": "previous_mrn",
            "value": f"OLD-{branch['code']}-{n + 1:05d}",
            "issuer": f"{branch['city']} Demo Clinic (invented)",
        }
        register_patient(
            actor=desk,
            facility=facility,
            data={
                "given_name": person.given_name,
                "family_name": person.family_name,
                "sex": person.sex,
                "date_of_birth": person.date_of_birth,
                "blood_group_reported": person.blood_group,
                "preferred_language": "hi" if ctx.country == "IN" and n % 2 else "en",
            },
            mobile=person.phone,
            address={
                "address_line1": f"House {n + 1}, {street}",
                "city": person.city,
                "state": branch["state"],
                "postal_code": branch["postal_code"],
            },
            relationships=relationships,
            identifier_items=[old_mrn] if n % 5 == 0 else [],
            privacy_notice="given",
            sms_consent=n % 3 != 0,
            email_consent=None,
        )
        ctx.add("patients")
    register_patient(
        actor=desk,
        facility=facility,
        data={
            "is_unknown": True,
            "sex": "male",
            "age_years": 45,
            "identification_note": "Demo: brought in by ambulance, unconscious, no papers",
        },
    )
    ctx.add("patients")


def _access_examples(ctx: Context, teams: list[dict]) -> None:
    from apps.access_control.models import RoleAssignment

    branch_admins = list(
        RoleAssignment.objects.filter(role__code="facility-administrator").select_related("user")
    )
    if len(branch_admins) >= 2:
        away, covering = branch_admins[0].user, branch_admins[1].user
        delegations.create_delegation(
            actor=ctx.admin,
            delegator=away,
            delegate=covering,
            ends_at=timezone.now() + timedelta(days=5),
            reason="Demo: annual leave cover",
        )
        ctx.add("cover arrangements")
    reviews.start_review(
        actor=ctx.admin, organization=ctx.organization, title="Quarterly access review"
    )
    ctx.add("access reviews")
    supplier = User.objects.filter(email=SUPPLIER_EMAIL).first()
    if supplier is None:
        return
    roles = {role.code: role for role in support.askable_roles()}
    done = support.request_access(
        actor=supplier,
        role=roles["organization-administrator"],
        reason="Demo: check the rota page error reported by the hospital",
        hours=2,
    )
    done = support.approve(actor=ctx.admin, access_id=done.pk, version=done.version, note="OK")
    support.end(actor=supplier, access_id=done.pk, version=done.version, reason="Work done")
    support.request_access(
        actor=supplier,
        role=roles["auditor"],
        reason="Demo: review the audit log after a sign-in problem",
        hours=1,
    )
    ctx.add("support access requests", 2)


# --- Entry point ----------------------------------------------------------------------------------


@transaction.atomic
def seed_hospital(hospital: Hospital, *, password: str | None, small: bool = False) -> Context:
    """Fill this deployment's (already provisioned) hospital. Refuses a second run."""
    check_safe()
    organization = Organization.objects.get()
    if Facility.objects.exists():
        raise DemoError("This hospital already has branches: the demo records are already in.")
    admin = active_administrators().order_by("date_joined").first()
    if admin is None:
        raise DemoError("Provision the hospital first (provision_organization).")
    ctx = Context(
        hospital=hospital,
        organization=organization,
        admin=admin,
        password=password,
        small=small,
        names=NameMaker(organization.country, hospital.key),
        random=random.Random(hospital.key),  # noqa: S311 - demo data, not security
        today=hospital_today(),
    )
    ensure_default_schemes(organization)  # MRN numbering (provisioning makes it too)
    invented = list(patients_for(hospital, per_branch=6 if small else 40, today=ctx.today))
    _hospital_settings(ctx)
    ctx.organization.refresh_from_db()
    hr_done = False
    teams = []
    for branch in hospital.branches[: 1 if small else None]:
        facility = _branch(ctx, branch)
        departments = _departments(ctx, facility)
        wards = _locations(ctx, facility, departments)
        team = _staff(ctx, facility, departments, branch)
        teams.append(team)
        if not hr_done:
            hr = _new_staff(
                ctx, HR_OFFICER, departments.get("ADMN", departments["EMR"]), None, branch
            )
            user = _account(ctx, hr, "hr", "HR / credentialing officer (whole hospital)")
            assign_role(
                actor=None,
                user=user,
                role=Role.objects.get(code="hr-credentialing-officer"),
                reason="Demo: HR officer",
            )
            records = _new_staff(
                ctx, WARD_CLERK, departments.get("ADMN", departments["EMR"]), None, branch
            )
            user = _account(ctx, records, "records", "Medical records officer (whole hospital)")
            assign_role(
                actor=None,
                user=user,
                role=Role.objects.get(code="medical-records-officer"),
                reason="Demo: medical records officer",
            )
            hr_done = True
        _privileges(ctx, team, departments)
        _rota(ctx, team, departments)
        _leave(ctx, team, departments)
        _equipment(ctx, facility, departments, wards)
        mine = [p for p in invented if p.branch == branch["code"]]
        _patients(ctx, facility, branch, mine)
    _access_examples(ctx, teams)
    return ctx
