"""Shared fixtures. All data is synthetic."""

import itertools

import pytest
from rest_framework.test import APIClient

from apps.access_control.services import assign_role, create_system_roles
from apps.facilities.models import Department, Facility
from apps.identity.models import User
from apps.organizations.services import provision_organization

_counter = itertools.count(1)


@pytest.fixture
def organization(db):
    return provision_organization(
        legal_name="Synthetic Health Pvt Ltd",
        display_name="Synthetic Health",
        country="IN",
        default_timezone="Asia/Kolkata",
        default_currency="INR",
    )


@pytest.fixture
def system_roles(organization):
    return create_system_roles(organization)


def _facility(organization, code):
    return Facility.objects.create(
        organization=organization,
        code=code,
        name=f"Facility {code.upper()}",
        facility_type=Facility.FacilityType.HOSPITAL,
        country="IN",
        state_region="Karnataka",
        city="Bengaluru",
        address_line1="1 Synthetic Road",
        postal_code="560001",
        timezone="Asia/Kolkata",
    )


@pytest.fixture
def facility_a(organization):
    return _facility(organization, "fac-a")


@pytest.fixture
def facility_b(organization):
    return _facility(organization, "fac-b")


@pytest.fixture
def department_a(facility_a):
    return Department.objects.create(
        organization_id=facility_a.organization_id,
        facility=facility_a,
        code="cardio",
        name="Cardiology",
        department_type=Department.DepartmentType.CLINICAL,
    )


@pytest.fixture
def make_user(organization):
    def factory(*, role=None, facility=None, department=None, password=None, **extra):
        n = next(_counter)
        user = User.objects.create_user(
            email=extra.pop("email", f"user{n}@synthetic.test"),
            display_name=extra.pop("display_name", f"Synthetic User {n}"),
            password=password,
            **extra,
        )
        if role is not None:
            assign_role(actor=None, user=user, role=role, facility=facility, department=department)
        return user

    return factory


@pytest.fixture
def admin_user(make_user, system_roles):
    return make_user(role=system_roles["organization-administrator"])


@pytest.fixture
def auditor_user(make_user, system_roles):
    return make_user(role=system_roles["auditor"])


@pytest.fixture
def client_for():
    def factory(user=None):
        client = APIClient()
        if user is not None:
            client.force_login(user)  # real session, so session/CSRF code paths are exercised
        return client

    return factory
