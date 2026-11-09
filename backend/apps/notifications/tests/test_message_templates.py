"""Hospital-editable message wording (HIMS-NOTIF-003; spec 4.1, 4.23). All data is synthetic."""

import pytest
from django.core import mail

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.identity import confirmation
from apps.identity.invitations import issue_invitation, send_invitation_email
from apps.notifications.message_catalog import BY_KEY, MESSAGES
from apps.notifications.message_templates import (
    check_wording,
    ensure_templates,
    fill,
    render,
)
from apps.notifications.models import MessageTemplate, Notification
from apps.notifications.services import send_message
from common.admin.tests.test_console_additions import console

LIST = "/api/v1/message-templates/"
INVITE = "identity.invitation"


@pytest.fixture
def client(client_for, admin_user):
    return client_for(admin_user)


@pytest.fixture
def invite(client):
    rows = client.get(LIST).json()
    return next(row for row in rows if row["key"] == INVITE)


def _save(client, row, **wording):
    body = {"version": row["version"], "subject": row["subject"], "body": row["body"], **wording}
    return client.patch(f"{LIST}{row['id']}/", body, format="json")


@pytest.mark.parametrize("spec", MESSAGES, ids=lambda spec: spec.code)
def test_every_standard_wording_passes_its_own_rules(spec):
    assert check_wording(spec, spec.subject, spec.body) == {}
    assert spec.required <= {variable.name for variable in spec.variables}


@pytest.mark.django_db
def test_the_list_shows_every_message_with_its_placeholders(client):
    rows = client.get(LIST).json()
    assert {row["key"] for row in rows} == set(BY_KEY)
    invite = next(row for row in rows if row["key"] == INVITE)
    assert invite["is_customised"] is False
    assert invite["subject"] == invite["standard_subject"]
    link = next(v for v in invite["variables"] if v["name"] == "link")
    assert link["required"] is True


@pytest.mark.django_db
def test_standard_wording_is_sent_as_before(organization, make_user):
    user = make_user(email="asha@example.test")
    invitation = issue_invitation(user=user)
    mail.outbox.clear()
    send_invitation_email(invitation)
    sent = mail.outbox[0]
    assert sent.subject == f"Activate your {organization.display_name} HIMS account"
    assert sent.body.startswith(f"Hello {user.display_name},\n\nYou have been invited")
    assert "/activate#token=" in sent.body
    assert not getattr(sent, "alternatives", None)
    logged = Notification.objects.get(template=INVITE)
    assert "#token=[hidden]" in logged.body and logged.category == "account"


@pytest.mark.django_db
def test_changed_wording_is_used_and_audited(client, invite, make_user):
    response = _save(
        client,
        invite,
        subject="Welcome to {{hospital}}",
        body="Dear {{name}}, please open {{link}} soon.\n",
    )
    assert response.status_code == 200, response.content
    assert response.json()["is_customised"] is True
    user = make_user(email="ravi@example.test")
    mail.outbox.clear()
    send_invitation_email(issue_invitation(user=user))
    sent = next(m for m in mail.outbox if m.to == ["ravi@example.test"])
    assert sent.subject.startswith("Welcome to ")
    assert sent.body.startswith(f"Dear {user.display_name}, please open http")
    event = AuditEvent.objects.get(action=AuditAction.MESSAGE_TEMPLATE_UPDATED)
    assert event.changes["after"]["subject"] == "Welcome to {{hospital}}"
    assert event.metadata["key"] == INVITE


@pytest.mark.django_db
def test_wrong_wording_is_refused_in_plain_language(client, invite):
    unknown = _save(client, invite, body="{{link}} {{patient_name}}")
    assert unknown.status_code == 400
    assert "patient_name" in str(unknown.json())
    no_link = _save(client, invite, body="Hello {{name}}")
    assert no_link.status_code == 400
    assert "link" in str(no_link.json())
    broken = _save(client, invite, body="{{link}} {{name}")
    assert broken.status_code == 400
    assert "two braces" in str(broken.json())
    assert MessageTemplate.objects.get(key=INVITE).body == ""


@pytest.mark.django_db
def test_the_standard_wording_saved_again_counts_as_standard(client, invite):
    assert _save(client, invite).json()["is_customised"] is False
    row = MessageTemplate.objects.get(key=INVITE)
    assert (row.subject, row.body) == ("", "")


@pytest.mark.django_db
def test_going_back_to_the_standard(client, invite):
    changed = _save(client, invite, body="Open {{link}}").json()
    back = client.post(
        f"{LIST}{invite['id']}/reset/", {"version": changed["version"]}, format="json"
    )
    assert back.status_code == 200
    assert back.json()["is_customised"] is False
    assert back.json()["body"] == BY_KEY[INVITE].body
    assert AuditEvent.objects.filter(action=AuditAction.MESSAGE_TEMPLATE_RESET).count() == 1


@pytest.mark.django_db
def test_changing_needs_the_current_version(client, invite):
    assert _save(client, invite, body="Open {{link}}").status_code == 200
    assert _save(client, invite, body="Please open {{link}}").status_code == 409


@pytest.mark.django_db
def test_preview_fills_made_up_values_and_saves_nothing(client, invite, organization):
    response = client.post(
        f"{LIST}{invite['id']}/preview/",
        {"subject": "For {{name}}", "body": "{{hospital}}: {{link}}"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["subject"] == "For Asha Verma"
    assert response.json()["body"].startswith(organization.display_name)
    assert MessageTemplate.objects.get(key=INVITE).body == ""
    assert not mail.outbox
    wrong = client.post(
        f"{LIST}{invite['id']}/preview/", {"subject": "x", "body": "no link"}, format="json"
    )
    assert wrong.status_code == 400


@pytest.mark.django_db
def test_a_value_that_looks_like_a_placeholder_stays_text():
    assert fill("Hi {{name}}", {"name": "{{link}}", "link": "secret"}) == "Hi {{link}}"


@pytest.mark.django_db
def test_stored_wording_that_no_longer_fits_falls_back_to_the_standard(organization):
    ensure_templates()
    MessageTemplate.objects.filter(key=INVITE).update(subject="x", body="{{gone}} {{link}}")
    subject, body = render(INVITE, {"name": "A", "link": "http://l", "expires": "soon"})
    assert subject == f"Activate your {organization.display_name} HIMS account"
    assert "http://l" in body


@pytest.mark.django_db
def test_an_empty_optional_value_leaves_no_gap(organization):
    _, body = render(
        "compliance.incident_reported", {"severity": "High", "deadlines": "", "link": "http://l"}
    )
    assert (
        body
        == "A security incident was reported (High severity).\n\nSee it here (sign-in needed): http://l\n"
    )


@pytest.mark.django_db
def test_values_cannot_break_the_subject_line(organization):
    subject, _ = render("access.cover_starting", {"colleague": "A\r\nBcc: x@example.test"})
    assert "\n" not in subject and "\r" not in subject


@pytest.mark.django_db
def test_only_people_with_the_permission_may_change(
    client_for, make_user, system_roles, invite, facility_a
):
    auditor = client_for(make_user(role=system_roles["auditor"]))
    assert auditor.get(LIST).status_code == 403
    assert (
        client_for(make_user(role=system_roles["facility-administrator"], facility=facility_a))
        .get(LIST)
        .status_code
        == 403
    )
    assert client_for(make_user()).get(LIST).status_code == 403


@pytest.mark.django_db
def test_changing_asks_to_confirm_it_is_you(client_for, admin_user, invite):
    client = client_for(admin_user)
    session = client.session
    session[confirmation.SESSION_CONFIRMED_KEY] = 0
    session.save()
    response = _save(client, invite, body="Open {{link}}")
    assert response.status_code == 403
    assert response.json()["code"] == "REAUTH_REQUIRED"
    assert MessageTemplate.objects.get(key=INVITE).body == ""


@pytest.mark.django_db
def test_a_message_goes_out_under_its_key_and_category(organization):
    sent = send_message(
        "identity.password_changed", to=["asha@example.test"], values={"name": "Asha"}
    )
    assert (sent.template, sent.category) == ("identity.password_changed", "security")
    assert organization.display_name in sent.subject


@pytest.mark.django_db
def test_console_lists_all_and_applies_the_same_checks(admin_user, client_for):
    client = console(admin_user, confirmed=True)
    page = client.get("/admin/notifications/messagetemplate/")
    assert page.status_code == 200
    assert MessageTemplate.objects.count() == len(MESSAGES)
    row = MessageTemplate.objects.get(key=INVITE)
    url = f"/admin/notifications/messagetemplate/{row.pk}/change/"
    shown = client.get(url).content.decode()
    assert "{{link}}" in shown and "must stay" in shown and "Asha Verma" in shown
    refused = client.post(url, {"subject": "", "body": "No link here"})
    assert refused.status_code == 200
    assert "must keep" in refused.content.decode()
    assert client.post(url, {"subject": "", "body": "Please open {{link}}"}).status_code == 302
    row.refresh_from_db()
    assert row.body == "Please open {{link}}" and row.updated_by == admin_user
    assert row.version == 2


@pytest.mark.django_db
def test_console_saving_asks_to_confirm_it_is_you(admin_user):
    client = console(admin_user, confirmed=False)
    client.get("/admin/notifications/messagetemplate/")
    row = MessageTemplate.objects.get(key=INVITE)
    url = f"/admin/notifications/messagetemplate/{row.pk}/change/"
    response = client.post(url, {"subject": "", "body": "Please open {{link}}"})
    assert response.status_code == 302 and "confirm" in response["Location"]
    row.refresh_from_db()
    assert row.body == ""


@pytest.mark.django_db
def test_console_action_goes_back_to_the_standard(admin_user):
    client = console(admin_user, confirmed=True)
    client.get("/admin/notifications/messagetemplate/")
    MessageTemplate.objects.filter(key=INVITE).update(body="Open {{link}}")
    row = MessageTemplate.objects.get(key=INVITE)
    client.post(
        "/admin/notifications/messagetemplate/",
        {"action": "use_standard_wording", "_selected_action": [str(row.pk)]},
    )
    row.refresh_from_db()
    assert row.body == ""
    assert AuditEvent.objects.filter(action=AuditAction.MESSAGE_TEMPLATE_RESET).count() == 1
