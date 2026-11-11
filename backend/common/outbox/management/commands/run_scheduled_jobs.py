"""Run every scheduled job whose time has come, once (spec 14; HIMS-OPS-023).

For hosts without an always-on scheduler: start this every minute from the host's timer
(Northflank scheduled job, GitHub Actions). With Celery beat running, do not use it.

python manage.py run_scheduled_jobs              # every due job
python manage.py run_scheduled_jobs --only NAME  # one job now, due or not
python manage.py run_scheduled_jobs --list       # the jobs and their last run
"""

from django.core.management.base import BaseCommand, CommandError

from common.outbox import scheduler


class Command(BaseCommand):
    help = "Run the scheduled jobs that are due (for hosts without Celery beat)."

    def add_arguments(self, parser):
        parser.add_argument("--only", help="Run this one job now, whether or not it is due.")
        parser.add_argument(
            "--list", action="store_true", dest="show", help="Show the jobs; run nothing."
        )

    def handle(self, *args, only=None, show=False, **options):
        if show:
            for job in scheduler.board():
                last = job["last_started_at"] or "never"
                self.stdout.write(
                    f"{job['name']:<26} every {job['every_seconds']:>6} s  last {last}  "
                    f"{job['last_outcome'] or '-'}"
                )
            return
        try:
            result = scheduler.run_due(only=only)
        except KeyError as exc:
            raise CommandError(f"No scheduled job called {only}.") from exc
        if result["busy"]:
            self.stdout.write("Another run is still going; nothing started.")
            return
        failed = [item for item in result["ran"] if item["error"]]
        for item in result["ran"]:
            self.stdout.write(f"{item['outcome']:<7} {item['job']} ({item['duration_ms']} ms)")
        self.stdout.write(f"Ran {len(result['ran'])} job(s), {len(failed)} failed.")
        if failed:
            raise CommandError(", ".join(f"{item['job']}: {item['error']}" for item in failed))
