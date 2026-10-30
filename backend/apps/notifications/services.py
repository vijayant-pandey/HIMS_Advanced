"""Notification service: every email and SMS HIMS sends goes through here (spec 4.23;
HIMS-NOTIF-001).

* Each message is logged (`notifications` table) with its outcome, so nothing fails silently.
* Delivery is tried at once (same behaviour as before for the sender). A failure does not break
  the action that caused it: the message is marked failed and retried every few minutes with a
  growing pause, up to ``HIMS_NOTIFICATION_MAX_ATTEMPTS`` times.
* The readable copy never contains sign-in links or other secrets (replaced by ``[hidden]``);
  the real text is kept encrypted only until it has been delivered.
* Channels: email through Django's ``EMAIL_BACKEND`` (console on a developer PC, SMTP such as
  Gmail or Amazon SES in hosted environments) and SMS through ``HIMS_SMS_BACKEND`` (console now).
"""

import logging
import re
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditAction, record_audit_event
from common import crypto
from common.exceptions import ConflictError

from .backends import sms_backend
from .models import Notification

logger = logging.getLogger(__name__)

Channel = Notification.Channel
Status = Notification.Status

HIDDEN = "[hidden]"
# Sign-in links carry their secret after "#token=" (activation, password reset).
_TOKEN = re.compile(r"(#token=)[^\s\"'<>]+")
_PHONE = re.compile(r"^\+[1-9]\d{7,14}$")
# Minutes to wait before attempt 2, 3, 4, 5…
_BACKOFF_MINUTES = (5, 15, 60, 240)


def redact(text: str, secrets: list[str] | tuple[str, ...] = ()) -> str:
    text = _TOKEN.sub(rf"\1{HIDDEN}", text)
    for secret in secrets:
        if secret:
            text = text.replace(secret, HIDDEN)
    return text


def _record(
    *, channel, recipients, subject, body, category, template, related, requested_by, secrets
) -> Notification:
    related_type, related_id = related or ("", "")
    return Notification.objects.create(
        channel=channel,
        category=category,
        template=template,
        recipients=list(recipients),
        subject=redact(subject, secrets)[:255],
        body=redact(body, secrets),
        body_encrypted=crypto.encrypt(body),
        related_type=related_type,
        related_id=str(related_id),
        requested_by_id=getattr(requested_by, "pk", None),
    )


def _deliver(notification: Notification) -> Notification:
    """One delivery attempt. Never raises: failures are recorded for a retry."""
    body = crypto.decrypt(notification.body_encrypted)
    notification.attempts += 1
    try:
        if notification.channel == Channel.EMAIL:
            send_mail(
                subject=notification.subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=notification.recipients,
            )
        else:
            backend = sms_backend()
            for phone in notification.recipients:
                backend.send(phone, body)
    except Exception as exc:  # any provider error; the detail is logged, not shown
        notification.last_error = f"{type(exc).__name__}: {str(exc)[:250]}"
        if notification.attempts >= settings.HIMS_NOTIFICATION_MAX_ATTEMPTS:
            notification.status = Status.GAVE_UP
            notification.next_attempt_at = None
        else:
            notification.status = Status.FAILED
            pause = _BACKOFF_MINUTES[min(notification.attempts - 1, len(_BACKOFF_MINUTES) - 1)]
            notification.next_attempt_at = timezone.now() + timedelta(minutes=pause)
        logger.warning(
            "notification_failed",
            extra={
                "notification_id": str(notification.pk),
                "template": notification.template,
                "attempt": notification.attempts,
                "error_type": type(exc).__name__,
            },
        )
    else:
        notification.status = Status.SENT
        notification.sent_at = timezone.now()
        notification.next_attempt_at = None
        notification.last_error = ""
        notification.body_encrypted = ""  # delivered: the secret-bearing copy is not kept
    notification.save()
    return notification


def _skip(notification: Notification, reason: str) -> Notification:
    notification.status = Status.SKIPPED
    notification.skip_reason = reason
    notification.body_encrypted = ""
    notification.save()
    return notification


def send_email(
    *,
    to,
    subject: str,
    body: str,
    category: str,
    template: str,
    related=None,
    requested_by=None,
    secrets=(),
) -> Notification:
    """Send one email to one or more addresses (all in "To", as before)."""
    recipients = [address for address in dict.fromkeys(to) if address]
    notification = _record(
        channel=Channel.EMAIL,
        recipients=recipients,
        subject=subject,
        body=body,
        category=category,
        template=template,
        related=related,
        requested_by=requested_by,
        secrets=secrets,
    )
    if not recipients:
        return _skip(notification, "Nobody to send it to.")
    return _deliver(notification)


def send_sms(
    *,
    to,
    body: str,
    category: str,
    template: str,
    related=None,
    requested_by=None,
    secrets=(),
) -> Notification:
    """Send one SMS to one or more phone numbers in international format (+91…, +1…)."""
    recipients = [phone for phone in dict.fromkeys(to) if phone]
    notification = _record(
        channel=Channel.SMS,
        recipients=recipients,
        subject="",
        body=body,
        category=category,
        template=template,
        related=related,
        requested_by=requested_by,
        secrets=secrets,
    )
    invalid = [phone for phone in recipients if not _PHONE.match(phone)]
    if not recipients or invalid:
        return _skip(notification, "No valid phone number (use +country code, e.g. +91…).")
    return _deliver(notification)


def retry_due(now=None) -> int:
    """Retry failed messages whose pause has passed. Safe to run from several workers."""
    now = now or timezone.now()
    retried = 0
    while True:
        with transaction.atomic():
            batch = list(
                Notification.objects.select_for_update(skip_locked=True)
                .filter(status=Status.FAILED, next_attempt_at__lte=now)
                .order_by("next_attempt_at")[:50]
            )
            for notification in batch:
                _deliver(notification)
        retried += len(batch)
        if len(batch) < 50:
            return retried


def retry_now(*, actor, notification_id, request=None) -> Notification:
    """A person asks for one failed message to be sent again at once."""
    with transaction.atomic():
        notification = Notification.objects.select_for_update().get(pk=notification_id)
        if notification.status not in (Status.FAILED, Status.GAVE_UP):
            raise ConflictError("Only failed messages can be sent again.", code="NOT_FAILED")
        if not notification.body_encrypted:
            raise ConflictError("This message can no longer be sent again.", code="NO_CONTENT")
        notification.status = Status.FAILED
        _deliver(notification)
        record_audit_event(
            action=AuditAction.NOTIFICATION_RETRIED,
            resource_type="notification",
            resource_id=notification.pk,
            actor=actor,
            request=request,
            metadata={"outcome": notification.status, "attempts": notification.attempts},
        )
    return notification


def send_test(*, actor, channel: str, to: str, request=None) -> Notification:
    """Check that email or SMS works: sends a short message with no personal data."""
    from apps.organizations.models import Organization

    organization = Organization.objects.only("display_name").first()
    hospital = organization.display_name if organization else "HIMS"
    text = (
        f"This is a test message from {hospital} HIMS, sent by {actor.display_name}. "
        "If you received it, messages are working. No action is needed."
    )
    if channel == Channel.SMS:
        notification = send_sms(
            to=[to],
            body=text,
            category="system",
            template="notifications.test",
            requested_by=actor,
        )
    else:
        notification = send_email(
            to=[to],
            subject=f"{hospital} HIMS: test message",
            body=text,
            category="system",
            template="notifications.test",
            requested_by=actor,
        )
    record_audit_event(
        action=AuditAction.NOTIFICATION_TEST_SENT,
        resource_type="notification",
        resource_id=notification.pk,
        actor=actor,
        request=request,
        metadata={"channel": channel, "outcome": notification.status},
    )
    return notification
