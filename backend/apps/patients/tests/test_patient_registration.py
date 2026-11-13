"""Patient registration with MRN, contacts, relationships, ID numbers and consents (HIMS-PAT-001;
spec 4.5, 13; P0 part 06 section 3). All people and numbers are invented."""

from datetime import date, timedelta

import pytest
from django.db import DatabaseError, transaction

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.features.catalog import F
from apps.features.services import ensure_hospital_rows, set_feature
from apps.numbering.models import NumberingScheme
from apps.numbering.services import ensure_default_schemes
from apps.organizations.dates import hospital_today
from apps.patients import demographics, identifiers
from apps.patients.models import (
    Patient,
    PatientAlias,
    PatientConsent,
    PatientContact,
    PatientIdentifier,
)
from common.admin.tests.test_console_additions import console
from common.outbox.models import OutboxEvent

LIST = "/api/v1/patients/"


def _aadhaar(first11: str) -> str:
    """A made-up 12-digit number whose check digit is right (not a real person's)."""
    return next(f"{first11}{d}" for d in "0123456789" if identifiers.verhoeff_ok(f"{first11}{d}"))


AADHAAR = _aadhaar("29999000011")
OTHER_AADHAAR = _aadhaar("29999000022")


@pytest.fixture
def schemes(organization):
    ensure_default_schemes(organization)


@pytest.fixture
def receptionist(make_user, system_roles, facility_a, schemes):
    return make_user(role=system_roles["receptionist"], facility=facility_a)


@pytest.fixture
def desk(client_for, receptionist):
    return client_for(receptionist)


def _body(facility, **extra):
    body = {
        "facility": str(facility.pk),
        "given_name": "Asha",
        "family_name": "Verma",
        "sex": "female",
        "age_years": 34,
        "mobile": "98765 43210",
        "privacy_notice": "given",
        "sms_consent": True,
        "email_consent": False,
    }
    body.update(extra)
    return body


def _register(client, facility, retry=None, **extra):
    headers = {"HTTP_IDEMPOTENCY_KEY": retry} if retry else {}
    return client.post(LIST, _body(facility, **extra), format="json", **headers)


def _fields(response) -> set[str]:
    return {error["field"] for error in response.json().get("errors", [])}


# --- Registration ----------------------------------------------------------------------------


@pytest.mark.django_db
def test_register_with_age_only_issues_mrn_and_estimates_birth_date(desk, facility_a):
    response = _register(
        desk, facility_a, address_line1="12 Lake Road", city="Delhi", state="Delhi"
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["mrn"] == "MRN-00000001"
    assert body["birth_date_estimated"] is True
    assert body["date_of_birth"].endswith("-07-01")  # 1 July of the birth year (D2)
    assert body["age"] == "34 y"
    kinds = sorted(c["kind"] for c in body["contacts"])
    assert kinds == ["address", "mobile"]
    mobile = next(c for c in body["contacts"] if c["kind"] == "mobile")
    assert mobile["phone"] == "+919876543210" and mobile["is_primary"]
    current = {c["kind"]: c["status"] for c in body["consents"]}
    assert current == {"privacy_notice": "given", "sms": "given", "email": "refused"}
    event = AuditEvent.objects.get(action=AuditAction.PATIENT_REGISTERED)
    assert event.resource_id == body["id"]
    assert event.facility_id == facility_a.pk
    outbox = OutboxEvent.objects.get(event_type="patient.registered")
    assert outbox.payload == {"patient_id": body["id"], "facility_id": str(facility_a.pk)}
    assert "Asha" not in str(outbox.payload)  # ids only in events


@pytest.mark.django_db
def test_double_click_registers_one_patient_with_one_mrn(desk, facility_a):
    first = _register(desk, facility_a, retry="register-asha-0001")
    second = _register(desk, facility_a, retry="register-asha-0001")
    assert first.status_code == second.status_code == 201
    assert first.json()["mrn"] == second.json()["mrn"]
    assert Patient.objects.count() == 1
    assert _register(desk, facility_a, retry="register-asha-0002").json()["mrn"] == "MRN-00000002"


@pytest.mark.django_db
def test_missing_name_sex_and_age_are_field_errors(desk, facility_a):
    response = desk.post(
        LIST, {"facility": str(facility_a.pk), "mobile": "9876543210"}, format="json"
    )
    assert response.status_code == 400
    assert "sex" in _fields(response)
    response = _register(desk, facility_a, given_name="", age_years=None)
    assert response.status_code == 400 and _fields(response) == {"given_name"}
    response = _register(desk, facility_a, age_years=None)
    assert response.status_code == 400 and _fields(response) == {"date_of_birth"}
    assert Patient.objects.count() == 0


@pytest.mark.django_db
def test_names_any_script_but_no_digits(desk, facility_a):
    assert _fields(_register(desk, facility_a, given_name="Asha2")) == {"given_name"}
    response = _register(desk, facility_a, given_name="  आशा  ", family_name="")
    assert response.status_code == 201
    assert response.json()["given_name"] == "आशा"
    assert response.json()["name"] == "आशा"  # one name is enough


@pytest.mark.django_db
def test_birth_date_rules(desk, facility_a):
    today = hospital_today()
    tomorrow = (today + timedelta(days=1)).isoformat()
    assert _fields(_register(desk, facility_a, age_years=None, date_of_birth=tomorrow)) == {
        "date_of_birth"
    }
    too_old = date(today.year - 131, 1, 1).isoformat()
    assert _fields(_register(desk, facility_a, age_years=None, date_of_birth=too_old)) == {
        "date_of_birth"
    }
    newborn = _register(
        desk, facility_a, age_years=None, date_of_birth=today.isoformat(), no_guardian_reason="x"
    )
    assert newborn.status_code == 201 and newborn.json()["age"] == "0 d"
    baby = _register(desk, facility_a, age_years=None, age_months=5, no_guardian_reason="x")
    assert baby.json()["age"] == "5 m" and baby.json()["birth_date_estimated"] is True


@pytest.mark.django_db
def test_mobile_or_no_phone(desk, facility_a):
    assert _fields(_register(desk, facility_a, mobile="")) == {"mobile"}
    assert _fields(_register(desk, facility_a, mobile="12345")) == {"mobile"}
    assert _fields(_register(desk, facility_a, mobile="+91 11 4000 0000")) == {"mobile"}  # landline
    response = _register(desk, facility_a, mobile="", has_no_phone=True)
    assert response.status_code == 201
    assert response.json()["has_no_phone"] is True and response.json()["contacts"] == []


@pytest.mark.django_db
def test_no_mrn_scheme_refuses_and_saves_nothing(desk, facility_a):
    NumberingScheme.objects.filter(document_type="mrn").update(is_active=False)
    response = _register(desk, facility_a)
    assert response.status_code == 409
    assert response.json()["code"] == "NUMBERING_NOT_CONFIGURED"
    assert Patient.objects.count() == PatientContact.objects.count() == 0


@pytest.mark.django_db
def test_unknown_patient_needs_how_they_arrived(desk, facility_a):
    response = _register(
        desk, facility_a, given_name="", family_name="", mobile="", is_unknown=True, sex="male"
    )
    assert _fields(response) == {"identification_note"}
    response = _register(
        desk,
        facility_a,
        given_name="",
        family_name="",
        mobile="",
        is_unknown=True,
        sex="male",
        identification_note="Brought by ambulance from MG Road",
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Unknown" and response.json()["is_unknown"] is True


@pytest.mark.django_db
def test_under_18_needs_a_guardian_or_a_reason(desk, facility_a):
    response = _register(desk, facility_a, age_years=9)
    assert response.status_code == 400 and _fields(response) == {"relationships"}
    mother = {"relation": "mother", "name": "Meera Verma", "phone": "9811122233"}
    response = _register(desk, facility_a, age_years=9, relationships=[mother])
    assert response.status_code == 201
    assert response.json()["relationships"][0]["phone"] == "+919811122233"
    assert response.json()["needs_guardian"] is False
    response = _register(desk, facility_a, age_years=9, no_guardian_reason="Emergency, alone")
    assert response.status_code == 201 and response.json()["needs_guardian"] is True
    event = AuditEvent.objects.filter(action=AuditAction.PATIENT_REGISTERED).latest("occurred_at")
    assert event.reason == "Emergency, alone"
    assert event.metadata == {"under_18_without_guardian": True}


# --- ID numbers ----------------------------------------------------------------------------


@pytest.mark.django_db
def test_id_numbers_are_encrypted_masked_and_never_shown(desk, facility_a):
    response = _register(
        desk,
        facility_a,
        identifiers=[{"kind": "aadhaar", "value": AADHAAR[:4] + " " + AADHAAR[4:]}],
    )
    assert response.status_code == 201, response.content
    shown = response.json()["identifiers"][0]
    assert shown["value_display"] == f"XXXX XXXX {AADHAAR[-4:]}"
    assert shown["verification"] == "unverified"
    row = PatientIdentifier.objects.get()
    assert AADHAAR not in row.value_encrypted
    assert identifiers.crypto.decrypt(row.value_encrypted) == AADHAAR
    assert AADHAAR not in response.content.decode()
    assert not any(AADHAAR in str(e.changes) for e in AuditEvent.objects.all())


@pytest.mark.django_db
def test_the_same_one_per_person_number_is_refused_on_a_second_patient(desk, facility_a):
    first = _register(desk, facility_a, identifiers=[{"kind": "aadhaar", "value": AADHAAR}])
    second = _register(
        desk, facility_a, given_name="Ravi", identifiers=[{"kind": "aadhaar", "value": AADHAAR}]
    )
    assert second.status_code == 409
    assert second.json()["code"] == "DUPLICATE_IDENTIFIER"
    assert first.json()["mrn"] in second.json()["detail"]  # points at the existing record
    assert Patient.objects.count() == 1  # nothing half-saved
    # Voter IDs are not one-per-person here: a family may share a typed reference.
    voter = {"kind": "voter_id", "value": "ABC1234567"}
    assert _register(desk, facility_a, identifiers=[voter]).status_code == 201
    assert _register(desk, facility_a, given_name="Ravi", identifiers=[voter]).status_code == 201


@pytest.mark.django_db
def test_wrong_numbers_and_other_countries_kinds_are_refused(desk, facility_a):
    typo = AADHAAR[:-1] + str((int(AADHAAR[-1]) + 1) % 10)
    response = _register(desk, facility_a, identifiers=[{"kind": "aadhaar", "value": typo}])
    assert _fields(response) == {"identifiers[0].value"}
    assert "check digit" in response.json()["errors"][0]["message"]
    response = _register(desk, facility_a, identifiers=[{"kind": "ssn", "value": "123-45-6789"}])
    assert "not used in this hospital's country" in response.json()["errors"][0]["message"]
    response = _register(desk, facility_a, identifiers=[{"kind": "previous_mrn", "value": "A1"}])
    assert _fields(response) == {"identifiers[0].value"}  # which hospital it is from


@pytest.mark.django_db
def test_an_ended_number_can_be_recorded_on_the_right_patient(desk, facility_a):
    wrong = _register(desk, facility_a, identifiers=[{"kind": "aadhaar", "value": AADHAAR}]).json()
    right = _register(desk, facility_a, given_name="Ravi").json()
    number = wrong["identifiers"][0]
    end = f"{LIST}{wrong['id']}/identifiers/{number['id']}/end/"
    assert (
        desk.post(end, {"version": number["version"], "reason": ""}, format="json").status_code
        == 400
    )
    response = desk.post(
        end, {"version": number["version"], "reason": "Typed on the wrong patient"}, format="json"
    )
    assert response.status_code == 200 and response.json()["is_active"] is False
    added = desk.post(
        f"{LIST}{right['id']}/identifiers/", {"kind": "aadhaar", "value": AADHAAR}, format="json"
    )
    assert added.status_code == 201
    assert PatientIdentifier.objects.count() == 2  # the ended one is kept


@pytest.mark.django_db
def test_registration_options_follow_the_country(desk, organization):
    kinds = {k["kind"] for k in desk.get(f"{LIST}registration-options/").json()["identifier_kinds"]}
    assert {"aadhaar", "abha_number", "voter_id"} <= kinds and "ssn" not in kinds
    organization.country = "US"
    organization.save(update_fields=["country"])
    kinds = {k["kind"] for k in desk.get(f"{LIST}registration-options/").json()["identifier_kinds"]}
    assert "ssn" in kinds and "aadhaar" not in kinds


# --- Who may do what -----------------------------------------------------------------------


@pytest.mark.django_db
def test_administrator_looks_up_and_opens_but_does_not_register(
    client_for, admin_user, desk, facility_a, schemes
):
    patient = _register(desk, facility_a).json()
    admin = client_for(admin_user)
    assert admin.get(LIST).json()["count"] == 1
    assert admin.get(f"{LIST}{patient['id']}/").status_code == 200
    assert _register(admin, facility_a, given_name="Ravi").status_code == 403


@pytest.mark.django_db
def test_branch_desk_registers_only_at_its_branch_but_finds_every_patient(
    client_for, make_user, system_roles, desk, facility_a, facility_b
):
    other_desk = client_for(make_user(role=system_roles["receptionist"], facility=facility_b))
    assert _register(desk, facility_b).status_code == 403
    patient = _register(other_desk, facility_b).json()
    assert desk.get(LIST).json()["count"] == 1  # one MRN in every facility
    assert desk.get(f"{LIST}{patient['id']}/").status_code == 200


@pytest.mark.django_db
def test_people_without_patient_access_get_nothing(
    client_for, auditor_user, make_user, system_roles, facility_a, desk
):
    patient = _register(desk, facility_a).json()
    for user in (auditor_user, make_user(role=system_roles["basic-staff"], facility=facility_a)):
        client = client_for(user)
        assert client.get(LIST).status_code == 403
        assert client.get(f"{LIST}{patient['id']}/").status_code == 403


@pytest.mark.django_db
def test_feature_off_at_a_branch_stops_registration_there(
    desk, admin_user, organization, facility_a
):
    ensure_hospital_rows(organization)
    set_feature(
        actor=admin_user,
        key=F.PATIENTS,
        facility=facility_a,
        enabled=False,
        reason="Front desk not trained yet",
        version=0,
    )
    response = _register(desk, facility_a)
    assert response.status_code in (403, 409)
    assert Patient.objects.count() == 0


@pytest.mark.django_db
def test_supplier_support_never_sees_patients_even_with_a_lent_admin_role(
    client_for, make_user, system_roles, desk, facility_a
):
    """Spec 7.2: support access must not silently reach patient records (HIMS-IAM-021 lends
    the administrator role; patient permissions are held back for the supplier's account)."""
    patient = _register(desk, facility_a).json()
    supplier = make_user(role=system_roles["supplier-support"])
    from apps.access_control.services import assign_role

    assign_role(actor=None, user=supplier, role=system_roles["organization-administrator"])
    client = client_for(supplier)
    assert client.get("/api/v1/facilities/").status_code == 200  # the lent role works
    assert client.get(LIST).status_code == 403
    assert client.get(f"{LIST}{patient['id']}/").status_code == 403
    grants = {g["permission"] for g in client.get("/api/v1/auth/me/").json()["grants"]}
    assert not {p for p in grants if p.startswith("patients.")}


@pytest.mark.django_db
def test_administrator_appoints_the_front_desk_but_the_supplier_cannot(
    client_for, admin_user, make_user, system_roles, facility_a
):
    """Administrators do not register patients, yet appointing the front desk is their job
    (patient permissions may be given by someone who may open patient records)."""
    body = {"role": str(system_roles["receptionist"].pk), "facility": str(facility_a.pk)}
    nurse = make_user()
    response = client_for(admin_user).post(
        "/api/v1/role-assignments/",
        {**body, "user": str(nurse.pk), "reason": "Front desk"},
        format="json",
    )
    assert response.status_code == 201, response.content
    supplier = make_user(role=system_roles["supplier-support"])
    from apps.access_control.services import assign_role

    assign_role(actor=None, user=supplier, role=system_roles["organization-administrator"])
    other = make_user()
    response = client_for(supplier).post(
        "/api/v1/role-assignments/",
        {**body, "user": str(other.pk), "reason": "Front desk"},
        format="json",
    )
    assert response.status_code == 403  # no patient access, so cannot hand it out either


# --- Reading is audited; the list shows the minimum ---------------------------------------


@pytest.mark.django_db
def test_opening_a_record_and_looking_up_an_mrn_are_audited(desk, facility_a):
    patient = _register(desk, facility_a).json()
    desk.get(f"{LIST}{patient['id']}/")
    viewed = AuditEvent.objects.get(action=AuditAction.PATIENT_RECORD_VIEWED)
    assert viewed.resource_id == patient["id"]
    found = desk.get(LIST, {"mrn": patient["mrn"].lower()}).json()
    assert found["count"] == 1
    searched = AuditEvent.objects.get(action=AuditAction.PATIENT_LIST_SEARCHED)
    assert searched.metadata == {"by": "mrn", "results": 1}
    assert patient["mrn"] not in str(searched.metadata)  # what was looked up is not kept


@pytest.mark.django_db
def test_the_list_shows_only_the_minimum(desk, facility_a):
    _register(
        desk,
        facility_a,
        identifiers=[{"kind": "aadhaar", "value": AADHAAR}],
        address_line1="12 Lake Road",
        state="Delhi",
    )
    row = desk.get(LIST).json()["results"][0]
    assert set(row) == {
        "id",
        "mrn",
        "name",
        "sex",
        "age",
        "birth_date_estimated",
        "phone_last4",
        "is_unknown",
        "status",
        "registered_facility",
        "registered_facility_name",
        "created_at",
        "matched_on",  # HIMS-PAT-002: what found the patient in a search (none here)
    }
    assert row["phone_last4"] == "…3210"
    assert row["matched_on"] is None


# --- Corrections ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_name_change_keeps_the_old_name_and_stale_edits_are_refused(desk, facility_a):
    patient = _register(desk, facility_a).json()
    url = f"{LIST}{patient['id']}/"
    response = desk.patch(
        url, {"version": patient["version"], "family_name": "Sharma"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["family_name"] == "Sharma"
    assert [a["name"] for a in response.json()["aliases"]] == ["Asha Verma"]
    assert "verma" in Patient.objects.get().search_name  # the old name still finds her
    stale = desk.patch(url, {"version": patient["version"], "occupation": "Teacher"}, format="json")
    assert stale.status_code == 409
    event = AuditEvent.objects.get(action=AuditAction.PATIENT_UPDATED)
    assert event.changes == {"before": {"family_name": "Verma"}, "after": {"family_name": "Sharma"}}


@pytest.mark.django_db
def test_contacts_are_added_made_main_and_ended_not_deleted(desk, facility_a):
    patient = _register(desk, facility_a).json()
    base = f"{LIST}{patient['id']}/contacts/"
    new = desk.post(
        base, {"kind": "mobile", "phone": "+91 99999 00001", "is_primary": True}, format="json"
    )
    assert new.status_code == 201 and new.json()["is_primary"] is True
    old = next(
        c
        for c in desk.get(f"{LIST}{patient['id']}/").json()["contacts"]
        if c["phone"] == "+919876543210"
    )
    assert old["is_primary"] is False  # one main mobile
    ended = desk.patch(
        f"{base}{old['id']}/", {"version": old["version"], "is_active": False}, format="json"
    )
    assert ended.status_code == 200 and ended.json()["is_active"] is False
    assert PatientContact.objects.count() == 2
    bad = desk.post(base, {"kind": "address", "city": "Delhi"}, format="json")
    assert _fields(bad) == {"state"}


@pytest.mark.django_db
def test_relationships_are_added_and_ended(desk, facility_a):
    patient = _register(desk, facility_a).json()
    base = f"{LIST}{patient['id']}/relationships/"
    added = desk.post(
        base,
        {"relation": "spouse", "name": "Ravi Verma", "is_emergency_contact": True},
        format="json",
    )
    assert added.status_code == 201
    rel = added.json()
    ended = desk.patch(
        f"{base}{rel['id']}/", {"version": rel["version"], "is_active": False}, format="json"
    )
    assert ended.json()["is_active"] is False
    own = desk.post(
        base, {"relation": "other", "name": "Self", "related_patient": patient["id"]}, format="json"
    )
    assert _fields(own) == {"related_patient"}


@pytest.mark.django_db
def test_consent_history_is_kept_and_cannot_be_changed(desk, facility_a):
    patient = _register(desk, facility_a).json()
    url = f"{LIST}{patient['id']}/consents/"
    withdrawn = desk.post(
        url, {"kind": "sms", "status": "withdrawn", "method": "signed_form"}, format="json"
    )
    assert withdrawn.status_code == 201
    nothing = desk.post(
        url, {"kind": "email", "status": "withdrawn", "method": "verbal"}, format="json"
    )
    assert nothing.status_code == 400  # email was refused, so there is nothing to withdraw
    sms = [
        c["status"]
        for c in desk.get(f"{LIST}{patient['id']}/").json()["consents"]
        if c["kind"] == "sms"
    ]
    assert sms == ["withdrawn", "given"]  # newest first; history kept
    with pytest.raises(DatabaseError), transaction.atomic():
        PatientConsent.objects.filter(kind="sms").update(note="changed")
    with pytest.raises(DatabaseError), transaction.atomic():
        PatientConsent.objects.all().delete()


@pytest.mark.django_db
def test_aliases_cannot_be_changed_or_deleted(desk, facility_a):
    patient = _register(desk, facility_a).json()
    desk.patch(f"{LIST}{patient['id']}/", {"version": 1, "given_name": "Aasha"}, format="json")
    assert PatientAlias.objects.count() == 1
    with pytest.raises(DatabaseError), transaction.atomic():
        PatientAlias.objects.update(given_name="X")


# --- Admin console -------------------------------------------------------------------------


@pytest.mark.django_db
def test_console_shows_patients_masked_and_audits_opening(admin_user, desk, facility_a):
    patient = _register(
        desk, facility_a, identifiers=[{"kind": "aadhaar", "value": AADHAAR}]
    ).json()
    client = console(admin_user, confirmed=True)
    page = client.get(f"/admin/patients/patient/{patient['id']}/change/")
    assert page.status_code == 200
    html = page.content.decode()
    assert patient["mrn"] in html and f"XXXX XXXX {AADHAAR[-4:]}" in html
    assert AADHAAR not in html
    assert AuditEvent.objects.filter(action=AuditAction.PATIENT_RECORD_VIEWED).count() == 1
    # Administrators look; they do not register (P0 part 04).
    assert client.get("/admin/patients/patient/add/").status_code == 403


@pytest.mark.django_db
def test_console_registers_through_the_service(make_user, system_roles, facility_a, schemes):
    officer = make_user(role=system_roles["organization-administrator"])
    from apps.access_control.services import assign_role

    assign_role(actor=None, user=officer, role=system_roles["medical-records-officer"])
    client = console(officer, confirmed=True)
    response = client.post(
        "/admin/patients/patient/add/",
        {
            "registered_facility": str(facility_a.pk),
            "given_name": "Kiran",
            "sex": "male",
            "age_years": "40",
            "mobile": "9876500011",
            "contacts-TOTAL_FORMS": "0",
            "contacts-INITIAL_FORMS": "0",
            "relationships-TOTAL_FORMS": "0",
            "relationships-INITIAL_FORMS": "0",
            "identifiers-TOTAL_FORMS": "0",
            "identifiers-INITIAL_FORMS": "0",
            "consents-TOTAL_FORMS": "0",
            "consents-INITIAL_FORMS": "0",
            "aliases-TOTAL_FORMS": "0",
            "aliases-INITIAL_FORMS": "0",
        },
    )
    assert response.status_code == 302, response.content.decode()[:2000]
    patient = Patient.objects.get()
    assert patient.mrn == "MRN-00000001" and patient.birth_date_estimated
    assert patient.contacts.get().phone == "+919876500011"
    assert AuditEvent.objects.filter(action=AuditAction.PATIENT_REGISTERED).count() == 1


# --- Rules on their own --------------------------------------------------------------------


def test_phone_numbers_are_stored_in_international_format():
    assert demographics.normalise_phone("098765 43210", country="IN") == "+919876543210"
    assert demographics.normalise_phone("(312) 555-0142", country="US") == "+13125550142"
    assert demographics.normalise_phone("+1 312 555 0142", country="IN") == "+13125550142"
    with pytest.raises(demographics.InvalidValue):
        demographics.normalise_phone("555 0142", country="US")


def test_estimated_birth_dates_give_back_the_age():
    for today in (date(2026, 3, 1), date(2026, 11, 12)):
        born = demographics.estimated_date_of_birth(today, years=34)
        assert born.month == 7 and born.day == 1
        assert demographics.years_between(born, today) == 34
    assert demographics.age_text(date(2026, 6, 12), date(2026, 11, 12)) == "5 m"
    assert demographics.age_text(date(2024, 11, 12), date(2026, 11, 12)) == "2 y"


def test_masks_show_at_most_the_last_four():
    assert identifiers.mask("ssn", "123456789") == "XXX-XX-6789"
    assert identifiers.mask("passport", "K1234567") == "XXXX4567"
    assert identifiers.mask("abha_address", "asha.verma@abdm") == "as********@abdm"
    assert identifiers.normalise("abha_number", "91-1234-5678-9012") == "91123456789012"
