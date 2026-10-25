import pytest
from django.core.management import call_command
from django.db import IntegrityError

from apps.access_control.models import RoleAssignment
from apps.identity.models import User
from apps.organizations.models import Organization
from apps.organizations.services import provision_organization
from common.exceptions import ConflictError


@pytest.mark.django_db
def test_provision_command_creates_org_roles_and_admin(monkeypatch):
    monkeypatch.setenv("ADMIN_PW", "Synthetic-Admin-Passw0rd")
    call_command(
        "provision_organization",
        "--legal-name=Synthetic Hospitals Inc",
        "--display-name=Synthetic Hospitals",
        "--country=US",
        "--timezone=America/Chicago",
        "--currency=USD",
        "--admin-email=admin@synthetic.test",
        "--admin-name=Synthetic Admin",
        "--admin-password-env=ADMIN_PW",
    )
    organization = Organization.objects.get()
    assert organization.deployment_id == "test-deployment"
    admin = User.objects.get(email="admin@synthetic.test")
    assert admin.check_password("Synthetic-Admin-Passw0rd")
    assert RoleAssignment.objects.get(user=admin).role.code == "organization-administrator"


@pytest.mark.django_db
def test_second_organization_is_refused(organization):
    with pytest.raises(ConflictError):
        provision_organization(
            legal_name="Other",
            display_name="Other",
            country="IN",
            default_timezone="Asia/Kolkata",
            default_currency="INR",
        )


@pytest.mark.django_db
def test_database_enforces_one_organization(organization):
    with pytest.raises(IntegrityError):
        Organization.objects.create(
            deployment_id="another",
            legal_name="Other",
            display_name="Other",
            country="IN",
            default_timezone="Asia/Kolkata",
            default_currency="INR",
        )


@pytest.mark.django_db
def test_update_requires_current_version(client_for, admin_user, organization):
    client = client_for(admin_user)
    ok = client.patch(
        "/api/v1/organization/", {"version": 1, "display_name": "Renamed"}, format="json"
    )
    assert ok.status_code == 200
    assert ok.json()["version"] == 2

    stale = client.patch(
        "/api/v1/organization/", {"version": 1, "display_name": "Stale"}, format="json"
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "STALE_RESOURCE"
