"""Restricted (VIP, staff) records and emergency access with review (HIMS-PAT-006; spec 4.5,
13.4; D14, D23; P0 parts 03 and 04). All people and numbers are invented."""

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.access_control.catalog import (
    MFA_REQUIRED_PERMISSIONS,
    NOT_FOR_ADMINISTRATORS,
    PATIENT_DATA_PERMISSIONS,
    SYSTEM_ROLES,
    P,
)
from apps.access_control.services import assign_role
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.notifications.models import Notification
from apps.numbering.services import ensure_default_schemes
from apps.patients import restricted
from apps.patients.models import EmergencyAccess, Patient
from apps.patients.services import register_patient
from common.admin.tests.test_console_additions import console
from common.exceptions import ConflictError

REASON = "Brought to the emergency room unconscious"


def _url(patient, part=""):
    return f"/api/v1/patients/{patient.pk}/{part}"


@pytest.fixture
def receptionist(make_user, system_roles, facility_a, organization):
    ensure_default_schemes(organization)
    return make_user(role=system_roles["receptionist"], facility=facility_a)


@pytest.fixture
def records_officer(make_user, system_roles, receptionist):
    return make_user(
        role=system_roles["medical-records-officer"],
        display_name="Records Officer",
        email="records@synthetic.test",
    )


@pytest.fixture
def doctor(make_user, system_roles, facility_a, department_a):
    return make_user(
        role=system_roles["department-head"],
        facility=facility_a,
        department=department_a,
        display_name="Head Of Cardiology",
    )


@pytest.fixture
def vip(receptionist, records_officer, facility_a):
    patient = register_patient(
        actor=receptionist,
        facility=facility_a,
        data={"given_name": "Kavya", "family_name": "Rao", "sex": "female", "age_years": 52},
        mobile="+919876500077",
        privacy_notice="given",
    )
    return restricted.set_restriction(
        actor=records_officer,
        patient_id=patient.pk,
        version=patient.version,
        restricted=True,
        restriction=Patient.Restriction.VIP,
        reason="Well-known public figure",
    )


def _search(client, text):
    return client.get("/api/v1/patients/", {"search": text}).json()


@pytest.mark.django_db
def test_a_restricted_record_is_hidden_from_search_except_by_its_exact_mrn(
    client_for, receptionist, records_officer, vip
):
    desk = client_for(receptionist)
    assert _search(desk, "Kavya Rao")["count"] == 0  # D23: hidden from general search
    assert _search(desk, "9876500077")["count"] == 0
    assert vip.pk not in [p["id"] for p in desk.get("/api/v1/patients/").json()["results"]]
    found = _search(desk, vip.mrn)  # the exact MRN: only that a restricted record exists
    assert found["count"] == 1
    row = found["results"][0]
    assert row["hidden"] is True and row["is_restricted"] is True
    assert (row["name"], row["age"], row["phone_last4"]) == ("", "", "")
    row = desk.get("/api/v1/patients/", {"mrn": vip.mrn}).json()["results"][0]
    assert row["hidden"] is True and row["name"] == ""
    # Medical records find it as usual.
    row = _search(client_for(records_officer), "Kavya Rao")["results"][0]
    assert (row["name"], row["hidden"], row["is_restricted"]) == ("Kavya Rao", False, True)


@pytest.mark.django_db
def test_opening_it_needs_the_permission_or_emergency_access(
    client_for, receptionist, records_officer, vip
):
    desk = client_for(receptionist)
    response = desk.get(_url(vip))
    assert response.status_code == 403
    assert response.json()["code"] == "RESTRICTED_RECORD"
    patch = desk.patch(_url(vip), {"version": vip.version, "occupation": "Teacher"}, format="json")
    assert patch.status_code == 403
    assert desk.get(_url(vip, "history/")).status_code == 403
    body = client_for(records_officer).get(_url(vip)).json()
    assert body["is_restricted"] is True and body["restriction"] == "vip"
    assert body["alerts"][0]["code"] == "restricted"
    assert body["emergency_access"] is None
    opened = AuditEvent.objects.get(action=AuditAction.PATIENT_RECORD_VIEWED)
    assert opened.metadata == {"restricted": True, "via": "restricted_permission"}


@pytest.mark.django_db
def test_emergency_access_opens_it_for_four_hours_and_tells_medical_records(
    client_for, doctor, records_officer, vip, django_capture_on_commit_callbacks
):
    api = client_for(doctor)
    assert api.get(_url(vip)).status_code == 403
    short = api.post(_url(vip, "emergency-access/"), {"reason": "urgent"}, format="json")
    assert short.status_code == 400
    with django_capture_on_commit_callbacks(execute=True):
        response = api.post(_url(vip, "emergency-access/"), {"reason": REASON}, format="json")
    assert response.status_code == 201, response.content
    access = EmergencyAccess.objects.get()
    assert abs(access.expires_at - access.created_at - timedelta(hours=4)) < timedelta(seconds=1)
    body = api.get(_url(vip)).json()
    assert body["emergency_access"]["id"] == str(access.pk)
    opened = AuditEvent.objects.filter(action=AuditAction.PATIENT_RECORD_VIEWED).latest(
        "occurred_at"
    )
    assert opened.metadata["via"] == "emergency_access"
    used = AuditEvent.objects.get(action=AuditAction.EMERGENCY_ACCESS_OPENED)
    assert used.reason == REASON and used.resource_id == str(vip.pk)
    # Medical records are told at once: who and when, never the patient or the reason.
    mail = Notification.objects.get(template="patients.emergency_access_opened")
    assert mail.recipients == ["records@synthetic.test"]
    assert "Head Of Cardiology" in mail.body
    for secret in (vip.mrn, "Kavya", "Rao", "unconscious"):
        assert secret not in mail.body and secret not in mail.subject
    again = api.post(_url(vip, "emergency-access/"), {"reason": REASON}, format="json")
    assert again.status_code == 409 and again.json()["code"] == "EMERGENCY_ACCESS_OPEN"
    assert api.post(_url(vip, "emergency-access/end/")).status_code == 200
    assert api.get(_url(vip)).status_code == 403  # ended: closed again


@pytest.mark.django_db
def test_emergency_access_closes_after_four_hours(client_for, doctor, vip):
    api = client_for(doctor)
    api.post(_url(vip, "emergency-access/"), {"reason": REASON}, format="json")
    access = EmergencyAccess.objects.get()
    access.expires_at = timezone.now() + timedelta(seconds=1)
    access.save()
    assert api.get(_url(vip)).status_code == 200  # still inside the 4 hours
    access.expires_at = timezone.now() - timedelta(seconds=1)
    access.save()
    assert api.get(_url(vip)).status_code == 403
    assert restricted.state_of(access) == restricted.State.TO_REVIEW


@pytest.mark.django_db
def test_emergency_access_only_where_it_is_needed(client_for, doctor, receptionist, vip):
    desk = client_for(receptionist)  # the front desk has no emergency access (P0 part 04)
    response = desk.post(_url(vip, "emergency-access/"), {"reason": REASON}, format="json")
    assert response.status_code == 403
    ordinary = register_patient(
        actor=receptionist,
        facility=vip.registered_facility,
        data={"given_name": "Asha", "sex": "female", "age_years": 30},
        mobile="+919876500078",
    )
    response = client_for(doctor).post(
        _url(ordinary, "emergency-access/"), {"reason": REASON}, format="json"
    )
    assert response.status_code == 409
    assert response.json()["code"] == "EMERGENCY_ACCESS_NOT_NEEDED"


@pytest.mark.django_db
def test_someone_else_from_medical_records_reviews_it_after_it_ends(
    client_for, doctor, records_officer, vip
):
    client_for(doctor).post(_url(vip, "emergency-access/"), {"reason": REASON}, format="json")
    records = client_for(records_officer)
    listed = records.get("/api/v1/patient-emergency-access/", {"state": "active"}).json()
    assert listed["count"] == 1
    access = listed["results"][0]
    assert (access["patient_mrn"], access["user_name"]) == (vip.mrn, "Head Of Cardiology")
    url = f"/api/v1/patient-emergency-access/{access['id']}/review/"
    early = records.post(url, {"outcome": "appropriate", "version": 1}, format="json")
    assert early.status_code == 409 and early.json()["code"] == "STILL_OPEN"
    client_for(doctor).post(_url(vip, "emergency-access/end/"))
    listed = records.get("/api/v1/patient-emergency-access/", {"state": "to_review"}).json()
    assert listed["count"] == 1
    version = listed["results"][0]["version"]
    no_note = records.post(url, {"outcome": "not_appropriate", "version": version}, format="json")
    assert no_note.status_code == 400
    done = records.post(
        url,
        {
            "outcome": "not_appropriate",
            "note": "No visit that day; ask the doctor",
            "version": version,
        },
        format="json",
    )
    assert done.status_code == 200, done.content
    assert done.json()["state"] == "reviewed"
    assert done.json()["reviewed_by_name"] == "Records Officer"
    reviewed = AuditEvent.objects.get(action=AuditAction.EMERGENCY_ACCESS_REVIEWED)
    assert reviewed.metadata["outcome"] == "not_appropriate"
    twice = records.post(url, {"outcome": "appropriate", "version": version + 1}, format="json")
    assert twice.json()["code"] == "ALREADY_REVIEWED"
    # The doctor cannot see the review list.
    assert client_for(doctor).get("/api/v1/patient-emergency-access/").status_code == 403


@pytest.mark.django_db
def test_nobody_reviews_their_own_emergency_access(records_officer, vip):
    own = EmergencyAccess.objects.create(
        organization_id=vip.organization_id,
        patient=vip,
        user=records_officer,
        reason=REASON,
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    with pytest.raises(ConflictError, match="Someone else"):
        restricted.review_emergency_access(
            actor=records_officer, access_id=own.pk, version=own.version, outcome="appropriate"
        )
    own.reviewed_by, own.reviewed_at, own.outcome = records_officer, timezone.now(), "appropriate"
    with pytest.raises(IntegrityError), transaction.atomic():
        own.save()  # the database refuses it too


@pytest.mark.django_db
def test_medical_records_restrict_and_lift_with_a_reason_and_see_every_opening(
    client_for, receptionist, records_officer, doctor, vip
):
    records = client_for(records_officer)
    current = records.get(_url(vip)).json()
    lift = {"restricted": False, "reason": "", "version": current["version"]}
    assert records.post(_url(vip, "restriction/"), lift, format="json").status_code == 400
    client_for(doctor).post(_url(vip, "emergency-access/"), {"reason": REASON}, format="json")
    client_for(doctor).get(_url(vip))
    openings = records.get("/api/v1/patients/restricted-openings/").json()
    assert [o["via"] for o in openings["results"]] == ["emergency_access", "restricted_permission"]
    assert openings["results"][0]["patient_mrn"] == vip.mrn
    assert AuditEvent.objects.filter(action=AuditAction.RESTRICTED_OPENINGS_VIEWED).count() == 1
    lift["reason"] = "The patient asked to lift it"
    response = records.post(_url(vip, "restriction/"), lift, format="json")
    assert response.status_code == 200, response.content
    assert response.json()["is_restricted"] is False
    lifted = AuditEvent.objects.get(action=AuditAction.PATIENT_RESTRICTION_LIFTED)
    assert lifted.reason == "The patient asked to lift it"
    assert lifted.changes["after"] == {"is_restricted": False, "restriction": ""}
    assert _search(client_for(receptionist), "Kavya Rao")["count"] == 1  # findable again
    # Only medical records restrict or see the openings.
    desk = client_for(receptionist)
    again = {"restricted": True, "restriction": "staff", "reason": REASON, "version": 3}
    assert desk.post(_url(vip, "restriction/"), again, format="json").status_code == 403
    assert desk.get("/api/v1/patients/restricted-openings/").status_code == 403


def test_who_holds_the_new_permissions():
    records = SYSTEM_ROLES["medical-records-officer"]["permissions"]
    assert P.PATIENTS_RESTRICTED in records and P.PATIENTS_RECORDS_CORRECT in records
    assert P.EMERGENCY_ACCESS not in records  # medical records open restricted records anyway
    assert P.EMERGENCY_ACCESS in SYSTEM_ROLES["department-head"]["permissions"]
    for code in (P.PATIENTS_RESTRICTED, P.PATIENTS_RECORDS_CORRECT, P.EMERGENCY_ACCESS):
        assert code not in SYSTEM_ROLES["organization-administrator"]["permissions"]
        assert code not in SYSTEM_ROLES["receptionist"]["permissions"]
        assert code in NOT_FOR_ADMINISTRATORS
        assert code in PATIENT_DATA_PERMISSIONS  # never the supplier's support account
        assert code in MFA_REQUIRED_PERMISSIONS  # P0 part 04: two-factor (★)


@pytest.mark.django_db
def test_console_hides_restricted_records_except_from_medical_records(
    admin_user, system_roles, vip, doctor
):
    change = f"/admin/patients/patient/{vip.pk}/change/"
    admin = console(admin_user, confirmed=True)
    page = admin.get("/admin/patients/patient/").content.decode()
    assert vip.mrn not in page
    assert admin.get(change).status_code == 302  # not found for them: back to the list
    contacts = admin.get("/admin/patients/patientcontact/").content.decode()
    assert "+919876500077" not in contacts
    assert admin.get("/admin/patients/emergencyaccess/").status_code == 403
    assign_role(actor=None, user=admin_user, role=system_roles["medical-records-officer"])
    admin = console(admin_user, confirmed=True)
    html = admin.get(change).content.decode()
    assert "Restricted record" in html and "hidden from patient search" in html
    opened = AuditEvent.objects.filter(action=AuditAction.PATIENT_RECORD_VIEWED).latest(
        "occurred_at"
    )
    assert opened.metadata["restricted"] is True
    restricted.open_emergency_access(actor=doctor, patient_id=vip.pk, reason=REASON)
    restricted.end_emergency_access(actor=doctor, patient_id=vip.pk)
    listing = admin.get("/admin/patients/emergencyaccess/").content.decode()
    assert "Ended, to review" in listing


@pytest.mark.django_db
def test_console_lifts_and_restricts_with_a_reason(admin_user, system_roles, vip):
    assign_role(actor=None, user=admin_user, role=system_roles["medical-records-officer"])
    client = console(admin_user, confirmed=True)
    url = f"/admin/patients/patient/{vip.pk}/change/"
    form = {
        "given_name": "Kavya",
        "family_name": "Rao",
        "date_of_birth": vip.date_of_birth.isoformat(),
        "birth_date_estimated": "on",
        "sex": "female",
        "restriction_reason": "",
        "restricted_as": "",
    }
    for prefix, count in (("contacts", 1), ("relationships", 0), ("identifiers", 0)):
        form |= {f"{prefix}-TOTAL_FORMS": str(count), f"{prefix}-INITIAL_FORMS": str(count)}
    for prefix, count in (("consents", 1), ("aliases", 0)):
        form |= {f"{prefix}-TOTAL_FORMS": str(count), f"{prefix}-INITIAL_FORMS": str(count)}
    page = client.post(url, form)
    assert page.status_code == 200  # the reason is missing: the form comes back
    assert "Give the reason" in page.content.decode()
    vip.refresh_from_db()
    assert vip.is_restricted
    form["restriction_reason"] = "The patient asked to lift it"
    assert client.post(url, form).status_code == 302
    vip.refresh_from_db()
    assert (vip.is_restricted, vip.restriction) == (False, "")
    form |= {"restricted_as": "staff", "restriction_reason": "Works in this hospital"}
    assert client.post(url, form).status_code == 302
    vip.refresh_from_db()
    assert (vip.is_restricted, vip.restriction) == (True, "staff")
    assert AuditEvent.objects.filter(action=AuditAction.PATIENT_RESTRICTED).count() == 2
