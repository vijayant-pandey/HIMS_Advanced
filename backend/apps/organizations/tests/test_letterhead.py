"""Hospital logo and letterhead (HIMS-ORG-006; spec 4.1). All data is synthetic."""

import io

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction
from apps.notifications.backends import ConsoleEmailBackend
from apps.notifications.services import send_email
from apps.organizations.logo import LOGO_MAX_BYTES
from apps.organizations.models import Organization
from common.admin.tests.test_console_additions import console

ORG = "/api/v1/organization/"
LOGO = "/api/v1/organization/logo/"
LETTERHEAD = "/api/v1/organization/letterhead/"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff" + b"\x00" * 32
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def _upload(client, content=PNG, name="logo.png"):
    return client.post(LOGO, {"file": SimpleUploadedFile(name, content)}, format="multipart")


def _details(organization, **fields):
    Organization.objects.filter(pk=organization.pk).update(**fields)


@pytest.fixture
def client(client_for, admin_user):
    return client_for(admin_user)


def _content(response) -> bytes:
    return b"".join(response.streaming_content)


@pytest.mark.django_db
def test_upload_show_replace_and_remove_the_logo(client):
    assert client.get(LOGO).status_code == 404
    uploaded = _upload(client)
    assert uploaded.status_code == 200, uploaded.content
    assert uploaded.json()["has_logo"] is True
    shown = client.get(LOGO)
    assert shown["Content-Type"] == "image/png"
    assert shown["X-Content-Type-Options"] == "nosniff"
    assert _content(shown) == PNG
    assert _upload(client, JPG, "photo.jpg").status_code == 200
    replaced = client.get(LOGO)
    assert replaced["Content-Type"] == "image/jpeg"
    assert _content(replaced) == JPG
    assert client.post(f"{LOGO}remove/").json()["has_logo"] is False
    assert client.get(LOGO).status_code == 404
    events = AuditEvent.objects.filter(action=AuditAction.ORGANIZATION_LOGO_CHANGED)
    assert [e.metadata["change"] for e in events.order_by("occurred_at")] == [
        "set",
        "set",
        "removed",
    ]


@pytest.mark.django_db
def test_the_stored_name_never_uses_the_uploaded_name(client):
    _upload(client, name="dr-asha-verma.png")
    name = Organization.objects.get().logo.name
    assert name.startswith("organization-logo/") and "asha" not in name


@pytest.mark.django_db
@pytest.mark.parametrize(
    "content,name,message",
    [
        (SVG, "logo.svg", "PNG or JPG"),
        (SVG, "logo.png", "PNG or JPG"),  # the name is not trusted
        (b"%PDF-1.7 not a picture", "logo.png", "PNG or JPG"),
        (PNG + b"\x00" * LOGO_MAX_BYTES, "big.png", "too large"),
    ],
    ids=["svg", "svg-named-png", "pdf-named-png", "too-large"],
)
def test_only_small_png_or_jpg_is_accepted(client, content, name, message):
    response = _upload(client, content, name)
    assert response.status_code == 400
    assert message in str(response.json())
    assert not Organization.objects.get().logo


@pytest.mark.django_db
def test_changing_the_logo_needs_the_permission_looking_only_a_sign_in(
    client, client_for, make_user
):
    _upload(client)
    person = client_for(make_user())
    assert person.get(LOGO).status_code == 200
    assert person.get(LETTERHEAD).status_code == 200
    assert _upload(person).status_code == 403
    assert person.post(f"{LOGO}remove/").status_code == 403
    assert client_for().get(LOGO).status_code in (401, 403)
    assert client_for().get(LETTERHEAD).status_code in (401, 403)


@pytest.mark.django_db
def test_letterhead_details_are_saved_with_the_hospital_details(client):
    version = client.get(ORG).json()["version"]
    response = client.patch(
        ORG,
        {
            "version": version,
            "letterhead_address": "1 Synthetic Road\nPune 411001",
            "letterhead_phone": "+91 20 0000 0000",
            "letterhead_email": "front.desk@example.test",
            "letterhead_website": "hospital.example.test",
            "letterhead_registration": "Reg. no. MH-1234",
            "letterhead_footer": "Helpline: 1800 000 000",
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    body = client.get(LETTERHEAD).json()
    assert body["lines"] == [
        "1 Synthetic Road",
        "Pune 411001",
        "+91 20 0000 0000 · front.desk@example.test · hospital.example.test",
        "Reg. no. MH-1234",
        "Helpline: 1800 000 000",
    ]
    assert body["has_logo"] is False
    event = AuditEvent.objects.filter(action=AuditAction.ORGANIZATION_UPDATED).latest("occurred_at")
    assert event.changes["after"]["letterhead_registration"] == "Reg. no. MH-1234"


@pytest.mark.django_db
def test_a_bad_letterhead_email_is_refused(client):
    version = client.get(ORG).json()["version"]
    response = client.patch(
        ORG, {"version": version, "letterhead_email": "not an email"}, format="json"
    )
    assert response.status_code == 400


def _send():
    return send_email(
        to=["asha@example.test"],
        subject="Hello",
        body="Open https://hims.example/activate#token=abc:DEF-1_2 now.\n<b>not bold</b>\n",
        category="account",
        template="identity.invitation",
    )


@pytest.mark.django_db
def test_without_a_letterhead_an_email_is_plain_text_as_before(organization):
    _send()
    sent = mail.outbox[0]
    assert sent.body.startswith("Open https://hims.example/activate#token=abc:DEF-1_2")
    assert sent.body.endswith("<b>not bold</b>\n")
    assert not getattr(sent, "alternatives", None) and not sent.attachments


@pytest.mark.django_db
def test_with_a_letterhead_an_email_carries_it_and_the_log_does_not(organization):
    _details(
        organization,
        letterhead_address="1 Synthetic Road",
        letterhead_footer="Helpline <1800>",
    )
    notification = _send()
    sent = mail.outbox[0]
    assert "1 Synthetic Road" in sent.body and "Helpline <1800>" in sent.body
    html = sent.alternatives[0][0]
    assert 'href="https://hims.example/activate#token=abc:DEF-1_2"' in html
    assert "&lt;b&gt;not bold&lt;/b&gt;" in html  # message text cannot become markup
    assert "Helpline &lt;1800&gt;" in html
    assert "cid:" not in html  # no logo set
    assert "1 Synthetic Road" not in notification.body
    assert notification.status == "sent"


@pytest.mark.django_db
def test_the_logo_travels_inside_the_email(client, organization):
    _upload(client)
    _send()
    sent = mail.outbox[-1]
    assert 'src="cid:hospital-logo"' in sent.alternatives[0][0]
    message = sent.message()
    assert message.get_content_subtype() == "related"
    parts = [part.get_content_type() for part in message.walk()]
    assert {"text/plain", "text/html", "image/png"} <= set(parts)
    image = next(part for part in message.walk() if part.get_content_type() == "image/png")
    assert image["Content-ID"] == "<hospital-logo>"
    assert image.get_payload(decode=True) == PNG


@pytest.mark.django_db
def test_a_missing_logo_file_does_not_hold_the_email_back(client, organization):
    _upload(client)
    logo = Organization.objects.get().logo
    logo.storage.delete(logo.name)
    notification = _send()
    assert notification.status == "sent"
    assert "cid:" not in mail.outbox[-1].alternatives[0][0]


@pytest.mark.django_db
def test_the_launcher_window_shows_the_link_not_the_encoded_logo(client, organization, settings):
    _upload(client, PNG + b"\x07" * 4000)
    _send()
    settings.HIMS_ENVIRONMENT = "local"
    stream = io.StringIO()
    ConsoleEmailBackend(stream=stream).send_messages([mail.outbox[-1]])
    printed = stream.getvalue()
    assert "https://hims.example/activate#token=abc:DEF-1_2" in printed
    assert "base64" not in printed and len(printed) < 2000


@pytest.mark.django_db
def test_console_shows_and_changes_the_letterhead(admin_user, client, organization):
    _upload(client)
    page = console(admin_user, confirmed=True)
    url = f"/admin/organizations/organization/{organization.pk}/change/"
    shown = page.get(url).content.decode()
    assert "/admin/organizations/organization/logo/" in shown
    assert page.get("/admin/organizations/organization/logo/")["Content-Type"] == "image/png"
    data = {
        "legal_name": organization.legal_name,
        "display_name": organization.display_name,
        "default_timezone": organization.default_timezone,
        "leave_year_start_month": 1,
        "letterhead_address": "2 Synthetic Road",
    }
    assert page.post(url, data).status_code == 302
    fresh = Organization.objects.get()
    assert fresh.letterhead_address == "2 Synthetic Road" and fresh.logo  # the logo stays
    refused = page.post(url, {**data, "logo": SimpleUploadedFile("x.png", SVG)})
    assert refused.status_code == 200
    assert "PNG or JPG" in refused.content.decode()
