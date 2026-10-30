"""SMS delivery backends (HIMS-NOTIF-001). Email uses Django's EMAIL_BACKEND.

Choose with ``HIMS_SMS_BACKEND`` (dotted path). The console backend prints each SMS to the
server output (the launcher window on a developer PC), like the console email backend. A real
provider (e.g. an Indian DLT-registered gateway or Twilio in the US) is added as another class
with the same ``send`` method.
"""

import sys

from django.conf import settings
from django.utils.module_loading import import_string


class SmsBackend:
    def send(self, to: str, body: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class ConsoleSmsBackend(SmsBackend):
    def send(self, to: str, body: str) -> None:
        line = "-" * 79
        sys.stdout.write(f"SMS to {to}\n{body}\n{line}\n")
        sys.stdout.flush()


class LocmemSmsBackend(SmsBackend):
    """Keeps messages in memory (tests)."""

    outbox: list[tuple[str, str]] = []

    def send(self, to: str, body: str) -> None:
        LocmemSmsBackend.outbox.append((to, body))


def sms_backend() -> SmsBackend:
    return import_string(settings.HIMS_SMS_BACKEND)()
