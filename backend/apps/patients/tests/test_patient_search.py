"""Patient search: MRN, phone, ID number and similar name, minimal results, audited (HIMS-PAT-002;
spec 4.5, 13.4, 28.6; P0 part 01 section 2, part 06). All people and numbers are invented."""

from datetime import date

import pytest
from django.db import connection, transaction

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.numbering.services import ensure_default_schemes
from apps.organizations.dates import hospital_today
from apps.patients import demographics, identifiers, search
from apps.patients.models import Patient
from apps.patients.services import end_identifier, register_patient, update_patient
from common.admin.tests.test_console_additions import console

LIST = "/api/v1/patients/"


def _aadhaar(first11: str) -> str:
    """A made-up 12-digit number whose check digit is right (not a real person's)."""
    return next(f"{first11}{d}" for d in "0123456789" if identifiers.verhoeff_ok(f"{first11}{d}"))


AADHAAR = _aadhaar("29999000033")


@pytest.fixture
def receptionist(make_user, system_roles, facility_a, organization):
    ensure_default_schemes(organization)
    return make_user(role=system_roles["receptionist"], facility=facility_a)


@pytest.fixture
def desk(client_for, receptionist):
    return client_for(receptionist)


@pytest.fixture
def add(receptionist, facility_a):
    def register(given, family="", *, age=40, sex="female", mobile="", **extra):
        data = {"given_name": given, "family_name": family, "sex": sex, "age_years": age}
        return register_patient(
            actor=receptionist,
            facility=facility_a,
            data={**data, "has_no_phone": not mobile},
            mobile=mobile,
            **extra,
        )

    return register


def _find(client, text, **params):
    response = client.get(LIST, {"search": text, **params})
    assert response.status_code == 200, response.content
    return response.json()


def _names(body) -> list[str]:
    return [row["name"] for row in body["results"]]


# --- Names --------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_similar_spelling_and_sound_alike_names_are_found(desk, add):
    add("Sunita", "Sharma")
    add("Lakshmi", "Iyer")
    add("Mohammad", "Khan", sex="male")
    add("Ravi", "Kumar", sex="male")
    assert _names(_find(desk, "suneeta")) == ["Sunita Sharma"]  # by sound
    assert _names(_find(desk, "sunitha sarma")) == ["Sunita Sharma"]
    assert _names(_find(desk, "laxmi")) == ["Lakshmi Iyer"]
    assert _names(_find(desk, "Muhammad khan")) == ["Mohammad Khan"]
    assert _names(_find(desk, "kumar ravi")) == ["Ravi Kumar"]  # any order
    assert _names(_find(desk, "sun")) == ["Sunita Sharma"]  # the start of a name
    body = _find(desk, "zebedee")
    assert body["count"] == 0 and body["results"] == []
    assert _find(desk, "laxmi")["results"][0]["matched_on"] == "name"


@pytest.mark.django_db
def test_best_match_comes_first(desk, add):
    add("Sunil", "Sharma", sex="male")
    add("Sunita", "Sharma")
    assert _names(_find(desk, "sunita sharma"))[0] == "Sunita Sharma"


@pytest.mark.django_db
def test_an_earlier_name_still_finds_the_patient(desk, add, receptionist):
    patient = add("Asha", "Verma")
    update_patient(
        actor=receptionist, patient_id=patient.pk, version=patient.version, family_name="Mehta"
    )
    assert _names(_find(desk, "asha verma")) == ["Asha Mehta"]
    assert _names(_find(desk, "mehta")) == ["Asha Mehta"]


@pytest.mark.django_db
def test_age_and_sex_narrow_a_name_search(desk, add):
    add("Sunita", "Sharma", age=34)
    add("Sunita", "Rao", age=61)
    add("Sunil", "Sharma", age=34, sex="male")
    assert sorted(_names(_find(desk, "sunita"))) == ["Sunita Rao", "Sunita Sharma"]
    assert _names(_find(desk, "sunita 60")) == ["Sunita Rao"]  # an age among the words, +/- 1
    assert _names(_find(desk, "sunita", age=35)) == ["Sunita Sharma"]
    assert _names(_find(desk, "sharma", sex="male")) == ["Sunil Sharma"]
    # A date of birth is not taken from the web address (spec 13.3): it is ignored, not used.
    born = date(hospital_today().year - 34, 7, 1).isoformat()
    assert len(_find(desk, "sunita", date_of_birth=born)["results"]) == 2


@pytest.mark.django_db
def test_too_short_or_too_many_asks_for_more_detail(desk, add):
    response = desk.get(LIST, {"search": "ab"})
    assert response.status_code == 400
    assert {e["field"] for e in response.json()["errors"]} == {"search"}
    for n in range(search.MAX_RESULTS + 3):
        add("Asha", "Verma", age=20 + n % 40)
    body = _find(desk, "asha")
    assert len(body["results"]) == search.MAX_RESULTS  # at most 50 (P0 part 01 section 2)
    assert body["count"] == search.MAX_RESULTS + 3  # the screen says "add more detail"
    assert body["next"] is None


# --- Numbers ------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_mrn_whole_or_only_its_number(desk, add):
    first = add("Asha", "Verma")
    for n in range(11):
        add("Ravi", "Kumar", sex="male", age=30 + n)
    body = _find(desk, first.mrn.lower())
    assert _names(body) == ["Asha Verma"] and body["results"][0]["matched_on"] == "mrn"
    assert _names(_find(desk, "1")) == ["Asha Verma"]  # MRN-00000001, not MRN-00000011
    assert _find(desk, "MRN-99999999")["count"] == 0


@pytest.mark.django_db
def test_phone_finds_everyone_who_gave_that_number(desk, add, receptionist):
    add("Asha", "Verma", mobile="+91 98765 43210")
    add("Meena", "Verma", mobile="098765 43210")  # the same family phone
    add("Ravi", "Kumar", sex="male", mobile="98765 11111")
    add(
        "Lata",
        "Rao",
        mobile="98765 22222",
        relationships=[{"relation": "next_of_kin", "name": "Anil Rao", "phone": "98765 43210"}],
    )
    body = _find(desk, "9876543210")
    assert sorted(_names(body)) == ["Asha Verma", "Meena Verma"]  # not the relative's phone
    assert {row["matched_on"] for row in body["results"]} == {"phone"}
    assert body["results"][0]["phone_last4"] == "…3210"  # still only the last 4 digits
    assert _find(desk, "98765 99999")["count"] == 0


@pytest.mark.django_db
def test_id_numbers_are_found_by_fingerprint_and_ended_ones_are_not(desk, add, receptionist):
    asha = add("Asha", "Verma", identifier_items=[{"kind": "aadhaar", "value": AADHAAR}])
    add(
        "Ravi",
        "Kumar",
        sex="male",
        identifier_items=[
            {"kind": "previous_mrn", "value": "OLD-77", "issuer": "Lake Clinic (invented)"}
        ],
    )
    spaced = f"{AADHAAR[:4]} {AADHAAR[4:8]} {AADHAAR[8:]}"
    body = _find(desk, spaced)
    assert _names(body) == ["Asha Verma"] and body["results"][0]["matched_on"] == "id_number"
    assert _names(_find(desk, "old-77")) == ["Ravi Kumar"]  # previous hospital's MRN
    row = asha.identifiers.get()
    end_identifier(
        actor=receptionist, identifier_id=row.pk, version=row.version, reason="Typed wrongly"
    )
    body = _find(desk, AADHAAR)
    assert body["count"] == 0  # a number nobody has: no results, not an error
    event = AuditEvent.objects.filter(action=AuditAction.PATIENT_LIST_SEARCHED).latest(
        "occurred_at"
    )
    assert event.metadata["by"] == "id_number" and event.metadata["results"] == 0


# --- Privacy and access -------------------------------------------------------------------------


@pytest.mark.django_db
def test_every_search_is_audited_without_what_was_typed(desk, add):
    add("Sunita", "Sharma", mobile="98765 43210")
    _find(desk, "suneeta", sex="female")
    _find(desk, "98765 43210")
    events = AuditEvent.objects.filter(action=AuditAction.PATIENT_LIST_SEARCHED).order_by(
        "occurred_at"
    )
    assert [e.metadata for e in events] == [
        {"by": "name", "results": 1, "filters": ["sex"]},
        {"by": "phone", "results": 1, "filters": []},
    ]
    assert "suneeta" not in str(events[0].metadata) and "43210" not in str(events[1].metadata)


@pytest.mark.django_db
def test_results_show_only_the_minimum(desk, add, client_for):
    add(
        "Sunita",
        "Sharma",
        mobile="98765 43210",
        identifier_items=[{"kind": "aadhaar", "value": AADHAAR}],
        address={"address_line1": "12 Lake Road", "state": "Delhi"},
    )
    row = _find(desk, "sunita")["results"][0]
    assert set(row) == set(desk.get(LIST).json()["results"][0])  # the same short list
    text = str(row)
    assert AADHAAR[-4:] not in text and "Lake Road" not in text and "43210" not in text


@pytest.mark.django_db
def test_search_needs_patient_access(client_for, auditor_user, make_user, system_roles, add):
    add("Sunita", "Sharma")
    basic = make_user(role=system_roles["basic-staff"])
    for user in (auditor_user, basic):
        assert client_for(user).get(LIST, {"search": "sunita"}).status_code == 403


@pytest.mark.django_db
def test_administrator_searches_but_supplier_support_cannot(
    client_for, admin_user, make_user, system_roles, add
):
    from apps.access_control.services import assign_role

    add("Sunita", "Sharma")
    assert _names(_find(client_for(admin_user), "suneeta")) == ["Sunita Sharma"]
    supplier = make_user(role=system_roles["supplier-support"])
    assign_role(actor=None, user=supplier, role=system_roles["organization-administrator"])
    assert client_for(supplier).get(LIST, {"search": "suneeta"}).status_code == 403


# --- Admin console ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_console_uses_the_same_search_and_audits_it(admin_user, add):
    add("Lakshmi", "Iyer", identifier_items=[{"kind": "aadhaar", "value": AADHAAR}])
    add("Ravi", "Kumar", sex="male")
    client = console(admin_user, confirmed=True)
    page = client.get("/admin/patients/patient/", {"q": "laxmi"}).content.decode()
    assert "Lakshmi Iyer" in page and "Ravi Kumar" not in page
    page = client.get("/admin/patients/patientidentifier/", {"q": AADHAAR}).content.decode()
    assert f"XXXX XXXX {AADHAAR[-4:]}" in page
    # What was typed stays in the search box and the filter links; the row itself is masked.
    echoed = page.replace(f'value="{AADHAAR}"', "").replace(f"q={AADHAAR}", "")
    echoed = echoed.replace(f"q%3D{AADHAAR}", "")  # the links back to this list
    assert AADHAAR not in echoed
    events = AuditEvent.objects.filter(action=AuditAction.PATIENT_LIST_SEARCHED)
    assert sorted(e.metadata["by"] for e in events) == ["id_number", "name"]
    assert all(e.metadata["in"] == "console" for e in events)
    page = client.get("/admin/patients/patient/", {"q": "ab"}).content.decode()
    assert "Type at least 3 letters" in page


# --- Indexes (spec 28.6) ------------------------------------------------------------------------


@pytest.mark.django_db
def test_name_search_can_use_its_indexes(add):
    for n in range(30):
        add("Sunita", f"Sharma{chr(97 + n % 26)}", age=20 + n)
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("ANALYZE patients")
        cursor.execute("SET LOCAL enable_seqscan = off")
        plan = search.find("suneeta").patients.explain()
    assert "patients_search_name_trgm" in plan or "patients_search_sounds_idx" in plan


# --- Sound keys (ADR-037) -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("one", "other"),
    [
        ("Sunita", "Suneeta"),
        ("Sunitha", "Sunita"),
        ("Mohammad", "Muhammad"),
        ("Lakshmi", "Laxmi"),
        ("Sharma", "Sarma"),
        ("Waseem", "Vaseem"),
        ("John", "Jon"),
        ("Smith", "Smyth"),
        ("Omar", "Umar"),
        ("Reddy", "Redy"),
    ],
)
def test_spelling_variants_sound_alike(one, other):
    assert demographics.sound_key(one) == demographics.sound_key(other)


def test_different_names_do_not_sound_alike_and_other_scripts_stay_as_written():
    assert demographics.sound_key("Ravi") != demographics.sound_key("Kumar")
    assert demographics.sound_key("Priya") != demographics.sound_key("Priyanka")
    assert demographics.sound_key("गीता") == "गीता"
    assert demographics.search_sounds("Asha Verma", "Asha Varma") == ["as", "vrm"]


@pytest.mark.django_db
def test_registration_stores_the_sound_keys(add):
    patient = Patient.objects.get(pk=add("Lakshmi", "Iyer").pk)
    assert patient.search_sounds == ["lxm", "ar"]
