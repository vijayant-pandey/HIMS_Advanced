"""The hospital's letterhead on emails (HIMS-ORG-006; spec 4.1).

With no letterhead set up, a message is sent exactly as plain text. With one, it goes as plain
text with the hospital's details at the end, plus an HTML copy with the logo at the top. The
message's text is unchanged, so the delivery log still holds the message and nothing else. The
logo travels inside the email: mail programs block pictures loaded from elsewhere, and HIMS does
not serve files to anyone who is not signed in.
"""

import logging
from email.mime.image import MIMEImage

from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.utils.html import format_html, format_html_join, urlize
from django.utils.safestring import mark_safe

from apps.organizations.logo import logo_type
from apps.organizations.models import Organization

logger = logging.getLogger(__name__)

_LOGO_ID = "hospital-logo"


def _logo_image(organization: Organization) -> MIMEImage | None:
    """The logo as an attachment shown in the email, or None if the file cannot be read: an
    email is never held back because of its logo."""
    if not organization.logo:
        return None
    try:
        with organization.logo.open("rb") as stored:
            kind = logo_type(stored)
            stored.seek(0)
            data = stored.read()
    except (OSError, ValueError) as exc:
        logger.warning("letterhead_logo_unreadable", extra={"error_type": type(exc).__name__})
        return None
    if kind is None:
        return None
    image = MIMEImage(data, _subtype=kind.split("/")[1])
    image.add_header("Content-ID", f"<{_LOGO_ID}>")
    image.add_header("Content-Disposition", "inline")
    return image


def _html(organization: Organization, body: str, details: list[str], has_logo: bool) -> str:
    logo = (
        format_html(
            '<img src="cid:{}" alt="{}" style="max-height:72px;max-width:240px"><br>',
            _LOGO_ID,
            organization.display_name,
        )
        if has_logo
        else ""
    )
    # urlize escapes the text; sign-in links stay clickable. Nothing here runs as a template.
    message = mark_safe(urlize(body, autoescape=True).replace("\n", "<br>\n"))  # noqa: S308
    return format_html(
        '<div style="font-family:Arial,sans-serif;font-size:14px;color:#222">'
        '<div style="border-bottom:2px solid #444;padding-bottom:8px;margin-bottom:16px">'
        "{}<strong>{}</strong></div><div>{}</div>"
        '<div style="border-top:1px solid #bbb;margin-top:24px;padding-top:8px;'
        'font-size:12px;color:#555">{}</div></div>',
        logo,
        organization.display_name,
        message,
        format_html_join(mark_safe("<br>"), "{}", ((line,) for line in details)),
    )


def email_with_letterhead(*, subject: str, body: str, recipients: list[str]) -> EmailMessage | None:
    """The email to send, or None when the hospital has not set up a letterhead."""
    organization = Organization.objects.first()
    if organization is None:
        return None
    details = organization.letterhead_lines()
    if not details and not organization.logo:
        return None
    text = f"{body.rstrip()}\n\n-- \n" + "\n".join([organization.display_name, *details]) + "\n"
    message = EmailMultiAlternatives(
        subject=subject, body=text, from_email=settings.DEFAULT_FROM_EMAIL, to=recipients
    )
    image = _logo_image(organization)
    message.attach_alternative(_html(organization, body, details, bool(image)), "text/html")
    if image is not None:
        message.mixed_subtype = "related"
        message.attach(image)
    return message
