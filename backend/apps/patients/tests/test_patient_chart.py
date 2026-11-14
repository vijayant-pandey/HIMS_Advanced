"""The patient chart: header, alerts and the record's history (HIMS-PAT-005; spec 15.3, 13.4;
P0 part 01 section 7, part 04). All people and numbers are invented."""

import pytest

from apps.access_control.catalog import PATIENT_DATA_PERMISSIONS, SYSTEM_ROLES, P
from apps.access_control.services import assign_role
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.numbering.services import ensure_default_schemes
from apps.patients.services import register_patient, update_patient
from common.admin.tests.test_console_additions import console


def _url(patient, part=""):
    return f"/api/v1/patients/{patient.pk}/{part}"


@pytest.fixture
def receptionist(make_user, system_roles, facility_a, organization):
    ensure_default_schemes(organization)
    return make_user(role=system_roles["receptionist"], facility=facility_a)


@pytest.fixture
def records_officer(make_user, system_roles, receptionist):
    return make_user(role=system_roles["medical-records-officer"], display_name="Records Officer")


@pytest.fixture
def add(receptionist, facility_a):
    def register(given, family="", *, age=40, mobile="+919876500001", **extra):
        return register_patient(
            actor=receptionist,
            facility=facility_a,
            data={
                "given_name": given,
                "family_name": family,
                "sex": "female",
                "age_years": age,
                "has_no_phone": not mobile,
            },
            mobile=mobile,
            **extra,
        )

    return register


@pytest.mark.django_db
def test_header_carries_the_allergy_status_and_the_alerts(client_for, receptionist, add):
    desk = client_for(receptionist)
    well = add("Asha", "Verma", privacy_notice="given")
    child = add("Meera", "Verma", age=10, no_guardian_reason="Brought by a teacher")
    body = desk.get(_url(well)).json()
    assert body["allergy_status"] == "not_asked"  # nothing recorded yet (D19; HIMS-CLIN-003)
    assert body["alerts"] == []
    body = desk.get(_url(child)).json()
    assert [a["code"] for a in body["alerts"]] == ["needs_guardian", "no_privacy_notice"]
    assert body["alerts"][0]["severity"] == "warning"
    assert body["needs_guardian"] is True
    unknown = register_patient(
        actor=receptionist,
        facility=well.registered_facility,
        data={
            "is_unknown": True,
            "sex": "male",
            "age_years": 45,
            "identification_note": "By ambulance",
        },
    )
    codes = [a["code"] for a in desk.get(_url(unknown)).json()["alerts"]]
    assert codes == ["unknown", "no_privacy_notice", "no_contact"]


@pytest.mark.django_db
def test_medical_records_see_who_opened_and_changed_the_record(
    client_for, receptionist, records_officer, add
):
    patient = add("Asha", "Verma", privacy_notice="given")
    client_for(receptionist).get(_url(patient))  # the front desk opens it
    update_patient(
        actor=receptionist, patient_id=patient.pk, version=patient.version, family_name="Mehta"
    )
    response = client_for(records_officer).get(_url(patient, "history/"))
    assert response.status_code == 200, response.content
    body = response.json()
    actions = [e["action"] for e in body["results"]]
    assert actions[:3] == [
        AuditAction.PATIENT_UPDATED,
        AuditAction.PATIENT_RECORD_VIEWED,
        AuditAction.PATIENT_REGISTERED,
    ]
    corrected = body["results"][0]
    assert corrected["changed"] == ["family name"]
    assert corrected["action_label"] == "Patient details corrected"
    assert corrected["actor_name"] == receptionist.display_name
    assert corrected["facility_name"] == patient.registered_facility.name
    assert "Verma" not in response.content.decode()  # field names only, never the values
    assert "Mehta" not in response.content.decode()
    # Seeing the history is itself audited, on the patient's record.
    seen = AuditEvent.objects.get(action=AuditAction.PATIENT_HISTORY_VIEWED)
    assert seen.actor_id == records_officer.pk and seen.resource_id == str(patient.pk)
    later = client_for(records_officer).get(_url(patient, "history/")).json()
    assert later["results"][0]["action"] == AuditAction.PATIENT_HISTORY_VIEWED


@pytest.mark.django_db
def test_only_medical_records_see_the_history(client_for, receptionist, admin_user, add):
    patient = add("Asha", "Verma")
    for user in (receptionist, admin_user):  # the front desk and the administrator: no
        assert client_for(user).get(_url(patient, "history/")).status_code == 403
    assert not AuditEvent.objects.filter(action=AuditAction.PATIENT_HISTORY_VIEWED).exists()


def test_history_belongs_to_medical_records_only():
    assert P.PATIENTS_HISTORY in SYSTEM_ROLES["medical-records-officer"]["permissions"]
    assert P.PATIENTS_HISTORY not in SYSTEM_ROLES["organization-administrator"]["permissions"]
    assert P.PATIENTS_HISTORY not in SYSTEM_ROLES["receptionist"]["permissions"]
    # Patient data: never the supplier's support account, whatever role it is lent (spec 7.2).
    assert P.PATIENTS_HISTORY in PATIENT_DATA_PERMISSIONS


@pytest.mark.django_db
def test_console_shows_the_chart_and_the_history_only_to_medical_records(
    admin_user, system_roles, add
):
    patient = add("Asha", "Verma", age=10, no_guardian_reason="Brought by a teacher")
    page = console(admin_user, confirmed=True).get(f"/admin/patients/patient/{patient.pk}/change/")
    html = page.content.decode()
    assert "Allergies not asked yet" in html
    assert "no parent or guardian recorded" in html
    assert "Who opened and changed it" not in html
    assign_role(actor=None, user=admin_user, role=system_roles["medical-records-officer"])
    page = console(admin_user, confirmed=True).get(f"/admin/patients/patient/{patient.pk}/change/")
    html = page.content.decode()
    assert "Who opened and changed it" in html
    assert "Patient registered (MRN issued)" in html
    seen = AuditEvent.objects.get(action=AuditAction.PATIENT_HISTORY_VIEWED)
    assert seen.metadata == {"in": "console"}
