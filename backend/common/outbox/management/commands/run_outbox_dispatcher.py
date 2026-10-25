"""Long-running outbox dispatcher, for a dedicated ECS service (ADR-012).

Celery beat also schedules ``outbox.dispatch_pending``; either (or both) may run because rows
are claimed with SKIP LOCKED.
"""

import signal
import time

from django.core.management.base import BaseCommand

from common.outbox.dispatcher import dispatch_pending


class Command(BaseCommand):
    help = "Continuously publish pending outbox events to the Celery broker."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=float, default=1.0, help="Idle sleep seconds.")
        parser.add_argument("--once", action="store_true", help="Dispatch one batch and exit.")

    def handle(self, *args, interval: float, once: bool, **options):
        stopping = False

        def _stop(*_):
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        while not stopping:
            dispatched = dispatch_pending()
            if once:
                self.stdout.write(f"Dispatched {dispatched} event(s).")
                return
            if dispatched == 0:
                time.sleep(interval)
