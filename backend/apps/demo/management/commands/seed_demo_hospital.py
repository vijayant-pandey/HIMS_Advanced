"""Fill this demo deployment's hospital with synthetic records (HIMS-QA-004).

Normally started by ``setup_demo_hospitals``, which creates the database and the settings file
first. Refuses anything that is not a demo deployment (``HIMS_DEPLOYMENT_ID`` = demo-...).
Demo sign-in accounts get the password in the environment variable named by ``--password-env``.
"""

import os

from django.core.management.base import BaseCommand, CommandError

from apps.demo.hospitals import by_key
from apps.demo.seed import DemoError, seed_hospital


class Command(BaseCommand):
    help = "Fill this demo hospital with synthetic branches, staff, beds, rota and equipment."

    def add_arguments(self, parser):
        parser.add_argument("--hospital", required=True, help="Key from apps/demo/hospitals.json")
        parser.add_argument("--password-env", help="Env var holding the demo accounts' password")
        parser.add_argument("--small", action="store_true", help="One branch, fewer records")

    def handle(self, *args, **opts):
        password = None
        if opts["password_env"]:
            password = os.environ.get(opts["password_env"])
            if not password:
                raise CommandError(f"Environment variable {opts['password_env']} is not set.")
        try:
            ctx = seed_hospital(by_key(opts["hospital"]), password=password, small=opts["small"])
        except (DemoError, KeyError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Filled {ctx.organization.display_name}:"))
        for what, count in ctx.counts.items():
            self.stdout.write(f"  {what}: {count}")
        self.stdout.write("Sign-in accounts (demo password):")
        for email, what in ctx.logins:
            self.stdout.write(f"  {email}  {what}")
