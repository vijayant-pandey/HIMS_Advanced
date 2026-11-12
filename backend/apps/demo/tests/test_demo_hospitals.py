"""HIMS-QA-004: demo hospitals with synthetic data. All data is invented."""

import os

import pytest
from django.core.management import call_command

from apps.access_control.models import AccessDelegation, SupportAccess
from apps.beds.models import Bed
from apps.demo import setup
from apps.demo.hospitals import all_hospitals, by_key
from apps.demo.patients import patients_for
from apps.demo.seed import SUPPLIER_EMAIL, DemoError, check_safe, seed_hospital
from apps.equipment.models import Equipment
from apps.facilities.location_models import Building, Ward
from apps.facilities.models import Department, Facility
from apps.identity.models import User
from apps.rosters.models import Shift
from apps.staff.models import StaffCredential, StaffMember


def test_five_indian_and_five_us_hospitals_with_three_branches_each():
    hospitals = all_hospitals()
    assert [h.country for h in hospitals].count("IN") == 5
    assert [h.country for h in hospitals].count("US") == 5
    assert all(len(h.branches) == 3 for h in hospitals)
    assert all("(Demo)" in h.display_name for h in hospitals)
    ports = [p for h in hospitals for p in (h.backend_port, h.frontend_port)]
    assert len(set(ports)) == len(ports)
    # Not the ports of this PC's own hospitals or the browser tests.
    assert not set(ports) & {8000, 8001, 8100, 8110, 5173, 5174, 5175, 5180, 5190}
    assert len({h.database for h in hospitals}) == 10


def test_only_demo_deployments_can_be_filled(settings):
    check_safe()  # the test deployment is allowed
    settings.HIMS_DEPLOYMENT_ID = "local-dev"
    with pytest.raises(DemoError, match="only into demo deployments"):
        check_safe()
    settings.HIMS_DEPLOYMENT_ID = "demo-in-sunrise"
    settings.HIMS_ENVIRONMENT = "production"
    with pytest.raises(DemoError, match="Refused"):
        check_safe()


@pytest.fixture
def provisioned(admin_user, make_user, system_roles):
    make_user(role=system_roles["supplier-support"], email=SUPPLIER_EMAIL)
    return admin_user


def test_a_small_demo_hospital_gets_records_for_every_screen(provisioned):
    ctx = seed_hospital(by_key("in-sunrise"), password="Synthetic-Demo-Passw0rd-0004", small=True)
    assert Facility.objects.get().name == "Sunrise Dwarka"
    assert Department.objects.count() == 6
    assert Department.objects.filter(head__isnull=False).count() == 6
    assert Building.objects.count() == 2
    assert Ward.objects.filter(ward_type="icu").exists() is False  # ICU is not in the small set
    assert Ward.objects.filter(ward_type="emergency").exists()
    assert Bed.objects.count() > 20
    assert Bed.objects.exclude(status=Bed.Status.AVAILABLE).exists()
    assert StaffMember.objects.count() >= 18
    assert StaffCredential.objects.filter(verification_status="verified").exists()
    assert Shift.objects.count() > 30
    assert Equipment.objects.filter(status=Equipment.Status.MAINTENANCE).exists()
    assert AccessDelegation.objects.count() == 0  # one branch administrator only
    assert SupportAccess.objects.count() == 2
    # Sign-in accounts work with the demo password and are listed for the product owner.
    accounts = dict(ctx.logins)
    assert "admin.dwk@in-sunrise.demo.test" in accounts
    assert "hr@in-sunrise.demo.test" in accounts
    user = User.objects.get(email="hod.dwk@in-sunrise.demo.test")
    assert user.check_password("Synthetic-Demo-Passw0rd-0004")
    with pytest.raises(DemoError, match="already"):
        seed_hospital(by_key("in-sunrise"), password=None, small=True)


def test_settings_file_and_child_processes_never_reuse_this_pcs_hospital(monkeypatch):
    hospital = by_key("us-lakeside")
    text = setup.env_text(hospital, "postgres://owner@localhost:5432/hims_demo_us_lakeside")
    values = setup._values(text)
    assert values["HIMS_DEPLOYMENT_ID"] == "demo-us-lakeside"
    assert values["HIMS_ENVIRONMENT"] == "local"
    assert values["HIMS_APP_BASE_URL"] == "http://localhost:5206"
    assert values["HIMS_SESSION_COOKIE_NAME"] == "hims_demo_us_lakeside_session"
    monkeypatch.setenv("DATABASE_URL", "postgres://owner@localhost:5432/hims")
    monkeypatch.setenv("HIMS_DEPLOYMENT_ID", "local-dev")
    monkeypatch.setenv("HIMS_DEMO_TEST_PW", "Synthetic-Demo-Passw0rd-0005")
    env = setup.child_env(hospital.env_file, values, "HIMS_DEMO_TEST_PW")
    assert env["DATABASE_URL"].endswith("/hims_demo_us_lakeside")
    assert env["HIMS_DEPLOYMENT_ID"] == "demo-us-lakeside"
    assert env["HIMS_ENV_FILE"] == ".env.demo-us-lakeside"
    assert env["HIMS_DEMO_TEST_PW"] == "Synthetic-Demo-Passw0rd-0005"


def test_patients_are_invented_the_same_way_every_time(capsys):
    hospital = by_key("in-ganga")
    first = list(patients_for(hospital, per_branch=5))
    assert first == list(patients_for(hospital, per_branch=5))
    assert len(first) == 15 and {p.branch for p in first} == {"LKO", "VNS", "PRY"}
    assert all(p.phone.startswith("+91 90000") for p in first)
    call_command("demo_patients", "--hospital=us-bluegrass", "--per-branch=2")
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("branch,given_name,family_name")
    assert out.count("+1 555 01") == 6


def test_setup_needs_the_password_first(monkeypatch):
    monkeypatch.delenv("HIMS_DEMO_PASSWORD", raising=False)
    with pytest.raises(DemoError, match="Set HIMS_DEMO_PASSWORD"):
        setup.set_up(
            by_key("in-sunrise"), password_env="HIMS_DEMO_PASSWORD", reset=False, small=True
        )
    assert "HIMS_DEMO_PASSWORD" not in os.environ
