"""Shared by the rota, leave balance and minimum staffing tests. All data is synthetic."""

from datetime import timedelta

import pytest

from apps.facilities.models import Department
from apps.organizations.dates import hospital_today
from apps.staff.models import Designation, StaffDepartmentAssignment, StaffMember

_n = iter(range(1, 10_000))


@pytest.fixture
def department_b(facility_a):
    return Department.objects.create(
        organization_id=facility_a.organization_id,
        facility=facility_a,
        code="ortho",
        name="Orthopaedics",
        department_type=Department.DepartmentType.CLINICAL,
    )


@pytest.fixture
def person(organization, make_user):
    """A working staff member with an account, posted in the given department."""

    def factory(department, *, given="Asha", account=True):
        n = next(_n)
        user = (
            make_user(email=f"rota{n}@synthetic.test", display_name=f"{given} Rota{n}")
            if account
            else None
        )
        staff = StaffMember.objects.create(
            organization=organization,
            user=user,
            employee_number=f"EMP-ROTA-{n}",
            given_name=given,
            family_name=f"Rota{n}",
            staff_type="nurse",
            joined_on="2026-01-05",
        )
        StaffDepartmentAssignment.objects.create(
            organization=organization,
            staff=staff,
            department=department,
            designation=Designation.objects.order_by("seniority").first(),
            valid_from=hospital_today() - timedelta(days=60),
            is_primary=True,
        )
        return staff

    return factory
