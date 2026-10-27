"""Everything is manageable in the admin console (product owner requirement, ADR-016).

Fails when a new model is added without an admin page or inline, so nothing is forgotten.
"""

import pytest
from django.apps import apps
from django.contrib import admin
from django.core.cache import cache
from django.test import Client

from apps.audit.models import AuditEvent
from apps.beds.models import Bed
from apps.facilities.models import Building, Floor, Room, Ward
from apps.identity.models import PasswordReset
from apps.numbering.models import NumberCounter, NumberingScheme
from apps.numbering.services import ensure_default_schemes

# Models deliberately not shown, with the reason.
NOT_IN_CONSOLE = {
    "identity.MfaRecoveryCode": "secret hashes; counts are shown on the two-factor device page",
}


@pytest.fixture(autouse=True)
def _clear_lockouts():
    cache.clear()


def console(user):
    client = Client()
    client.force_login(user)
    return client


def _inline_models():
    found = set()
    for model_admin in admin.site._registry.values():
        for inline in model_admin.inlines:
            found.add(inline.model)
    return found


def test_every_hims_model_is_in_the_admin_console():
    inline_models = _inline_models()
    missing = [
        model._meta.label
        for model in apps.get_models()
        if model.__module__.startswith(("apps.", "common."))
        and model not in admin.site._registry
        and model not in inline_models
        and model._meta.label not in NOT_IN_CONSOLE
    ]
    assert missing == [], (
        f"Add these to the admin console (or NOT_IN_CONSOLE with a reason): {missing}"
    )


@pytest.mark.django_db
def test_every_console_page_opens(admin_user, auditor_user, organization):
    ensure_default_schemes(organization)
    administrator, auditor = console(admin_user), console(auditor_user)
    for model, model_admin in admin.site._registry.items():
        if not model.__module__.startswith(("apps.", "common.")):
            continue
        meta = model._meta
        client = auditor if model is AuditEvent else administrator
        url = f"/admin/{meta.app_label}/{meta.model_name}/"
        assert client.get(url).status_code == 200, url
        if model_admin.has_add_permission(type("R", (), {"user": admin_user})()):
            assert client.get(f"{url}add/").status_code == 200, f"{url}add/"


def _structure(facility):
    building = Building.objects.create(facility=facility, code="main", name="Main")
    floor = Floor.objects.create(building=building, level=1, name="First")
    ward = Ward.objects.create(floor=floor, code="w1", name="Ward 1", ward_type="general")
    room = Room.objects.create(ward=ward, code="r1", name="Room 1", room_type="general")
    bed = Bed.objects.create(room=room, code="b01", bed_type="general")
    return room, bed


@pytest.mark.django_db
def test_console_changes_bed_status_through_the_rules(admin_user, facility_a):
    _room, bed = _structure(facility_a)
    client = console(admin_user)
    url = f"/admin/beds/bed/{bed.pk}/change/"
    form = {"bed_type": "general", "is_active": "on", "new_status": "maintenance"}

    missing_reason = client.post(url, form)
    assert missing_reason.status_code == 200  # form shown again with the error
    bed.refresh_from_db()
    assert bed.status == Bed.Status.AVAILABLE

    client.post(url, {**form, "new_status_reason": "Broken side rail"})
    bed.refresh_from_db()
    assert bed.status == Bed.Status.MAINTENANCE
    assert bed.status_reason == "Broken side rail"
    assert AuditEvent.objects.filter(action="bed.status.changed", resource_id=str(bed.pk)).exists()


@pytest.mark.django_db
def test_room_page_lists_beds_and_location_codes_cannot_change(admin_user, facility_a):
    room, bed = _structure(facility_a)
    page = console(admin_user).get(f"/admin/facilities/room/{room.pk}/change/")
    assert b"b01" in page.content  # beds inline on the room page

    bed.code = "b99"
    with pytest.raises(Exception, match="Codes cannot change"):
        bed.full_clean()


@pytest.mark.django_db
def test_console_sends_password_reset_link(admin_user, make_user):
    user = make_user(password="Synthetic-Reset-Passw0rd-2026")
    response = console(admin_user).post(
        "/admin/identity/user/",
        {"action": "send_password_reset", "_selected_action": [str(user.pk)]},
    )
    assert response.status_code == 302
    assert PasswordReset.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_console_continues_numbering_from_previous_system(admin_user, organization):
    ensure_default_schemes(organization)
    scheme = NumberingScheme.objects.get(document_type="mrn")
    client = console(admin_user)
    url = f"/admin/numbering/numberingscheme/{scheme.pk}/change/"
    form = {
        "prefix": "MRN",
        "separator": "-",
        "period": "none",
        "year_format": "full",
        "financial_year_start_month": 4,
        "padding": 8,
        "start_at": 1,
        "is_active": "on",
        "continue_from": 54322,
    }
    assert client.post(url, form).status_code == 302
    assert NumberCounter.objects.get(scheme=scheme).last_value == 54321
    assert AuditEvent.objects.filter(action="numbering.next_number.set").exists()
