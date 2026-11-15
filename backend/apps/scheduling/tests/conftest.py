"""Shared by the doctor schedule, appointment and OPD queue tests (HIMS-OPD-001, -002, -003).
All data is synthetic."""

from datetime import time, timedelta

import pytest

from apps.facilities.models import Department, DepartmentHours
from apps.numbering.services import ensure_default_schemes
from apps.organizations.dates import hospital_today
from apps.patients.services import register_patient
from apps.scheduling import services
from apps.staff.models import Designation, StaffDepartmentAssignment, StaffMember

_n = iter(range(1, 10_000))
API = "/api/v1"


@pytest.fixture
def client_for(client_for):
    """The shared fixture, sending JSON by default (the API accepts nothing else)."""

    def factory(user=None):
        client = client_for(user)
        client.default_format = "json"
        return client

    return factory


@pytest.fixture
def department_b(facility_a):
    return Department.objects.create(
        organization_id=facility_a.organization_id,
        facility=facility_a,
        code="ortho",
        name="Orthopaedics",
        department_type=Department.DepartmentType.CLINICAL,
    )


def _designation():
    """The catalog's most junior job title, or one made here when the database is truly empty
    (tests with ``transaction=True`` run without the catalog's data migration)."""
    found = Designation.objects.order_by("seniority").first()
    if found is None:
        found = Designation.objects.create(
            code="synthetic-medical-officer",
            name="Medical officer",
            category=Designation.Category.MEDICAL,
            seniority=2,
        )
    return found


@pytest.fixture
def doctor(organization, make_user):
    """A working doctor (with an account) posted in the given department since 60 days ago."""

    def factory(department, *, given="Ravi", staff_type="doctor", account=True):
        n = next(_n)
        user = (
            make_user(email=f"opd{n}@synthetic.test", display_name=f"Dr {given} Opd{n}")
            if account
            else None
        )
        staff = StaffMember.objects.create(
            organization=organization,
            user=user,
            employee_number=f"EMP-OPD-{n}",
            given_name=given,
            family_name=f"Opd{n}",
            staff_type=staff_type,
            joined_on="2026-01-05",
        )
        StaffDepartmentAssignment.objects.create(
            organization=organization,
            staff=staff,
            department=department,
            designation=_designation(),
            valid_from=hospital_today() - timedelta(days=60),
            is_primary=True,
        )
        return staff

    return factory


@pytest.fixture
def hod(make_user, system_roles, department_a):
    return make_user(
        role=system_roles["department-head"],
        facility=department_a.facility,
        department=department_a,
        display_name="Synthetic Head",
    )


@pytest.fixture
def front_desk(make_user, system_roles, facility_a):
    return make_user(
        role=system_roles["receptionist"], facility=facility_a, display_name="Synthetic Desk"
    )


def open_hours(department, *, opens=time(8), closes=time(18), days=range(6)):
    """Monday to Saturday 08:00-18:00 unless told otherwise."""
    DepartmentHours.objects.filter(department=department).delete()
    for day in days:
        DepartmentHours.objects.create(
            department=department, weekday=day, opens_at=opens, closes_at=closes
        )


def next_weekday(weekday: int, *, after=None):
    """The next given weekday (0 = Monday) after today (or after a day), never today."""
    day = (after or hospital_today()) + timedelta(days=1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day


# --- Appointments and the OPD queue (HIMS-OPD-002, HIMS-OPD-003) --------------------------------

ALL_DAYS = range(7)


@pytest.fixture
def ravi(doctor, department_a):
    return doctor(department_a, given="Ravi")


@pytest.fixture
def mohan(doctor, department_a):
    return doctor(department_a, given="Mohan")


@pytest.fixture
def sessions(ravi, mohan, department_a):
    """Every day 09:00-13:00 for both doctors, 10-minute slots; Ravi allows one extra booking."""
    for staff, extra in ((ravi, 1), (mohan, 0)):
        services.add_sessions(
            actor=None,
            staff=staff,
            department=department_a,
            weekdays=ALL_DAYS,
            start_time=time(9),
            end_time=time(13),
            valid_from=hospital_today(),
            extra_bookings_allowed=extra,
        )


@pytest.fixture
def desk(make_user, system_roles, facility_a, organization):
    ensure_default_schemes(organization)
    return make_user(
        role=system_roles["receptionist"], facility=facility_a, display_name="Synthetic Desk"
    )


@pytest.fixture
def patient(desk, facility_a):
    def factory(given="Asha", family="Kumar"):
        return register_patient(
            actor=desk,
            facility=facility_a,
            data={
                "given_name": given,
                "family_name": family,
                "sex": "female",
                "age_years": 40,
                "has_no_phone": True,
            },
            privacy_notice="given",
        )

    return factory
