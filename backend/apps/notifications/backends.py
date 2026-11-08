"""SMS delivery backends (HIMS-NOTIF-001). Email uses Django's EMAIL_BACKEND.

Choose with ``HIMS_SMS_BACKEND`` (dotted path). The console backend prints each SMS to the
server output (the launcher window on a developer PC), like the console email backend. A real
provider (e.g. an Indian DLT-registered gateway or Twilio in the US) is added as another class
with the same ``send`` method.

Outside a developer PC (HIMS-SEC-019) the server output is the server log, so the console
backends do not print secrets there: an SMS is printed without its text, an email with sign-in
links and codes hidden. Production settings swap Django's console email backend for
:class:`ConsoleEmailBackend` for that reason.
"""

import sys

from django.conf import settings
from django.core.mail.backends import console
from django.utils.module_loading import import_string

from common.environment import LOCAL_ENVIRONMENTS
from common.log_safety import scrub

LINE = "-" * 79


def _shows_everything() -> bool:
    return settings.HIMS_ENVIRONMENT in LOCAL_ENVIRONMENTS


class SmsBackend:
    def send(self, to: str, body: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class ConsoleSmsBackend(SmsBackend):
    def send(self, to: str, body: str) -> None:
        if not _shows_everything():
            to, body = f"{to[:3]}…{to[-2:]}", "(text not printed outside a developer PC)"
        sys.stdout.write(f"SMS to {to}\n{body}\n{LINE}\n")
        sys.stdout.flush()


class ConsoleEmailBackend(console.EmailBackend):
    """Django's console email backend. Outside a developer PC only the subject and the body are
    printed, with secrets hidden (Django's encoded copy of the message could not be checked)."""

    def write_message(self, message):
        if _shows_everything():
            return super().write_message(message)
        self.stream.write(
            f"Email to {len(message.recipients())} recipient(s): {scrub(message.subject)}\n"
            f"{scrub(message.body)}\n{LINE}\n"
        )


class LocmemSmsBackend(SmsBackend):
    """Keeps messages in memory (tests)."""

    outbox: list[tuple[str, str]] = []

    def send(self, to: str, body: str) -> None:
        LocmemSmsBackend.outbox.append((to, body))


def sms_backend() -> SmsBackend:
    return import_string(settings.HIMS_SMS_BACKEND)()
