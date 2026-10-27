"""Feature settings, HIMS-ORG-004. All data is synthetic."""

import pytest
from django.core.cache import cache
from django.test import Client, override_settings

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.facilities.models import Building
from apps.features.catalog import BY_KEY, FEATURES, F
from apps.features.models import FeatureFlag
from apps.features.services import ensure_hospital_rows, is_enabled, set_feature
from apps.organizations.models import Organization
from common.exceptions import StaleResourceError

API = "/api/v1"


@pytest.fixture(autouse=True)
def _clear_throttles():
    cache.clear()


@pytest.fixture
def rows(organization):
    ensure_hospital_rows(organization)


def change(client, key, body):
    return client.post(f"{API}/features/{key}/change/", body, format="json")


# --- Deciding on/off ------------------------------------------------------------------------


@pytest.mark.django_db
def test_defaults_hospital_and_facility_settings(rows, admin_user, facility_a, facility_b):
    assert is_enabled(F.LOCATIONS, facility_id=facility_a.pk) is True  # default on
    set_feature(actor=admin_user, key=F.LOCATIONS, enabled=False, reason="Not used yet", version=1)
    assert is_enabled(F.LOCATIONS, facility_id=facility_a.pk) is False  # hospital-wide off
    set_feature(
        actor=admin_user,
        key=F.LOCATIONS,
        facility=facility_a,
        enabled=True,
        reason="Pilot at branch A",
        version=0,
    )
    assert is_enabled(F.LOCATIONS, facility_id=facility_a.pk) is True  # facility override wins
    assert is_enabled(F.LOCATIONS, facility_id=facility_b.pk) is False
    set_feature(
        actor=admin_user, key=F.LOCATIONS, enabled=None, reason="Back to default", version=2
    )
    assert is_enabled(F.LOCATIONS, facility_id=facility_b.pk) is True


@pytest.mark.django_db
def test_planned_and_other_country_features_cannot_be_switched_on(rows, admin_user, client_for):
    with pytest.raises(Exception, match="Not available yet"):
        set_feature(
            actor=admin_user, key="patients.registration", enabled=True, reason="x", version=1
        )
    Organization.objects.update(country="US")
    features = {f["key"]: f for f in client_for(admin_user).get(f"{API}/features/").json()}
    assert features["integrations.abdm"]["offered_in_country"] is False  # India only
    assert features["insurance.us_payers"]["offered_in_country"] is True


@pytest.mark.django_db
def test_hospital_only_feature_cannot_be_set_per_facility(rows, admin_user, facility_a):
    with pytest.raises(Exception, match="whole hospital only"):
        set_feature(
            actor=admin_user,
            key=F.TWO_FACTOR_FOR_EVERYONE,
            facility=facility_a,
            enabled=True,
            reason="x",
            version=0,
        )


@pytest.mark.django_db
def test_changes_need_a_reason_the_current_version_and_are_audited(rows, admin_user):
    with pytest.raises(Exception, match="Say why"):
        set_feature(actor=admin_user, key=F.LOCATIONS, enabled=False, reason=" ", version=1)
    set_feature(actor=admin_user, key=F.LOCATIONS, enabled=False, reason="Audit test", version=1)
    with pytest.raises(StaleResourceError):
        set_feature(actor=admin_user, key=F.LOCATIONS, enabled=True, reason="Old copy", version=1)
    event = AuditEvent.objects.get(action=AuditAction.FEATURE_FLAG_CHANGED)
    assert event.reason == "Audit test"
    assert event.changes == {
        "before": {"setting": "default", "effective": True},
        "after": {"setting": "off", "effective": False},
    }


@pytest.mark.django_db
def test_every_feature_gets_a_hospital_row_once(organization):
    assert len(ensure_hospital_rows(organization)) == len(FEATURES)
    assert ensure_hospital_rows(organization) == []
    assert FeatureFlag.objects.filter(enabled__isnull=False).count() == 0  # nothing switched


# --- Live features ----------------------------------------------------------------------------


@pytest.mark.django_db
def test_forgot_password_can_be_turned_off(rows, admin_user, make_user):
    make_user(email="nurse@synthetic.test", password="Synthetic-Nurse-Passw0rd-2026")
    url = f"{API}/auth/password-reset/request/"
    assert (
        Client()
        .post(url, {"email": "nurse@synthetic.test"}, content_type="application/json")
        .status_code
        == 202
    )
    set_feature(
        actor=admin_user,
        key=F.SELF_SERVICE_PASSWORD_RESET,
        enabled=False,
        reason="Policy",
        version=1,
    )
    for email in ("nurse@synthetic.test", "nobody@synthetic.test"):  # same answer: no enumeration
        response = Client().post(url, {"email": email}, content_type="application/json")
        assert response.status_code == 409
        assert response.json()["code"] == "FEATURE_DISABLED"


@pytest.mark.django_db
@override_settings(HIMS_MFA_REQUIRED_FOR_PRIVILEGED=True)
def test_two_factor_for_everyone(rows, admin_user, make_user, system_roles, facility_a, client_for):
    nurse = make_user(role=system_roles["basic-staff"], facility=facility_a)
    assert client_for(nurse).get(f"{API}/facilities/").status_code == 200
    set_feature(
        actor=admin_user, key=F.TWO_FACTOR_FOR_EVERYONE, enabled=True, reason="Policy", version=1
    )
    assert client_for(nurse).get(f"{API}/facilities/").json()["code"] == "MFA_SETUP_REQUIRED"


@pytest.mark.django_db
def test_locations_can_be_closed_for_one_facility(
    rows, admin_user, client_for, facility_a, facility_b
):
    client = client_for(admin_user)
    for facility in (facility_a, facility_b):
        client.post(
            f"{API}/buildings/",
            {"facility": str(facility.pk), "code": "main", "name": "Main"},
            format="json",
        )
    set_feature(
        actor=admin_user,
        key=F.LOCATIONS,
        facility=facility_a,
        enabled=False,
        reason="Branch A not live yet",
        version=0,
    )
    tree = client.get(f"{API}/facilities/{facility_a.pk}/locations/")
    assert tree.status_code == 409
    assert tree.json()["code"] == "FEATURE_DISABLED"
    assert client.get(f"{API}/facilities/{facility_b.pk}/locations/").status_code == 200
    listing = client.get(f"{API}/buildings/").json()["results"]
    assert [row["facility"] for row in listing] == [str(facility_b.pk)]
    building_a = Building.objects.get(facility=facility_a)
    assert client.get(f"{API}/buildings/{building_a.pk}/").status_code == 409
    new = client.post(
        f"{API}/buildings/",
        {"facility": str(facility_a.pk), "code": "x", "name": "X"},
        format="json",
    )
    assert new.status_code == 409
    console = Client()
    console.force_login(admin_user)
    assert console.get(f"/admin/facilities/building/{building_a.pk}/change/").status_code == 200


# --- API --------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_sees_every_feature_and_changes_one(rows, admin_user, client_for):
    client = client_for(admin_user)
    features = client.get(f"{API}/features/").json()
    assert len(features) == len(FEATURES)
    registration = next(f for f in features if f["key"] == "patients.registration")
    assert registration["available"] is False and registration["planned_phase"] == "Phase 2"
    abdm = next(f for f in features if f["key"] == "integrations.abdm")
    assert abdm["offered_in_country"] is True  # India hospital
    stedi = next(f for f in features if f["key"] == "insurance.us_payers")
    assert stedi["offered_in_country"] is False

    flag = next(f for f in features if f["key"] == F.LOCATIONS)
    body = {"setting": "off", "reason": "Board decision", "version": flag["hospital"]["version"]}
    response = change(client, F.LOCATIONS, body)
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["hospital"]["setting"] == "off"
    assert response.json()["hospital"]["updated_by_name"] == admin_user.display_name
    assert change(client, F.LOCATIONS, body).status_code == 409  # old version


@pytest.mark.django_db
def test_planned_feature_change_is_refused_by_the_api(rows, admin_user, client_for):
    response = change(
        client_for(admin_user),
        "patients.registration",
        {"setting": "on", "reason": "Try", "version": 1},
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_facility_admin_changes_only_own_facility(
    rows, client_for, make_user, system_roles, facility_a, facility_b
):
    client = client_for(make_user(role=system_roles["facility-administrator"], facility=facility_a))
    listing = client.get(f"{API}/features/", {"facility": str(facility_a.pk)}).json()
    assert {f["scope"] for f in listing} == {"facility"}
    body = {"setting": "off", "reason": "Not live yet", "version": 0}
    assert change(client, F.LOCATIONS, {**body, "facility": str(facility_a.pk)}).status_code == 200
    assert change(client, F.LOCATIONS, {**body, "facility": str(facility_b.pk)}).status_code == 403
    assert change(client, F.LOCATIONS, {**body, "version": 1}).status_code == 403  # hospital-wide
    assert client.get(f"{API}/features/", {"facility": str(facility_b.pk)}).status_code == 404


@pytest.mark.django_db
def test_staff_without_permission_cannot_see_settings(
    client_for, make_user, system_roles, facility_a
):
    client = client_for(make_user(role=system_roles["basic-staff"], facility=facility_a))
    assert client.get(f"{API}/features/").status_code == 403


@pytest.mark.django_db
def test_effective_features_before_and_after_sign_in(rows, admin_user, client_for, facility_a):
    anonymous = Client().get(f"{API}/features/effective/").json()
    assert anonymous == {
        "hospital": {F.SELF_SERVICE_PASSWORD_RESET: True},
        "facilities": {},
    }
    signed_in = client_for(admin_user).get(f"{API}/features/effective/").json()
    assert signed_in["hospital"][F.TWO_FACTOR_FOR_EVERYONE] is False
    assert signed_in["facilities"][str(facility_a.pk)][F.LOCATIONS] is True


@pytest.mark.django_db
def test_managing_features_requires_two_factor(make_user, system_roles, facility_a):
    from apps.identity.mfa import is_required

    with override_settings(HIMS_MFA_REQUIRED_FOR_PRIVILEGED=True):
        assert is_required(
            make_user(role=system_roles["facility-administrator"], facility=facility_a)
        )


@pytest.mark.django_db
def test_console_changes_a_feature_with_audit(rows, admin_user):
    row = FeatureFlag.objects.get(key=F.LOCATIONS, facility__isnull=True)
    console = Client()
    console.force_login(admin_user)
    response = console.post(
        f"/admin/features/featureflag/{row.pk}/change/",
        {"enabled": "false", "reason": "Closed from the console"},
    )
    assert response.status_code == 302
    row.refresh_from_db()
    assert row.enabled is False and row.updated_by == admin_user and row.version == 2
    assert AuditEvent.objects.filter(action="admin.featureflag.updated").exists()
    assert BY_KEY[row.key].name == "Locations and beds"
