"""Print how the background events stand (HIMS-PLAT-014; spec 14.3).

Exits with status 1 when something needs a look (failed events, or events waiting longer than
HIMS_OUTBOX_STUCK_MINUTES), so it can be used by monitoring. What to do then:
docs/runbooks/outbox-and-background-jobs.md.
"""

from django.core.management.base import BaseCommand, CommandError

from common.outbox.maintenance import outbox_health


class Command(BaseCommand):
    help = "Show waiting, retried and failed background events; exit 1 if any need a look."

    def handle(self, *args, **options):
        health = outbox_health()
        last = health["last_cleanup"]
        self.stdout.write(
            f"Waiting: {health['waiting']} (oldest {health['oldest_waiting_minutes']} minutes), "
            f"being retried: {health['retrying']}, failed: {health['failed']}, "
            f"dismissed: {health['dismissed']}, done in the last 24 hours: "
            f"{health['published_last_24h']}."
        )
        self.stdout.write(
            f"Last clean-up: {last['at']:%Y-%m-%d %H:%M} UTC, {last['events_deleted']} deleted."
            if last
            else "Last clean-up: never."
        )
        if not health["attention"]:
            self.stdout.write(self.style.SUCCESS("OK: nothing needs a look."))
            return
        for problem in health["attention"]:
            self.stderr.write(f"- {problem}")
        raise CommandError(
            "Needs a look: see docs/runbooks/outbox-and-background-jobs.md (Background jobs page)."
        )
