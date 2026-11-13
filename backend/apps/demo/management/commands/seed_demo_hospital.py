"""Fill this demo deployment's hospital with synthetic records (HIMS-QA-004).

Normally started by ``setup_demo_hospitals``, which creates the database and the settings file
first. Refuses anything that is not a demo deployment (``HIMS_DEPLOYMENT_ID`` = demo-...).
Demo sign-in accounts get the password in the environment variable named by ``--password-env``.

``--hosted-development`` (2026-11-13): fills the hosted Development hospital (Render and Neon,
synthetic data only) from the PC with ``HIMS_ENV_FILE=.env.hosted-dev``; refused anywhere but
``HIMS_ENVIRONMENT=development``. Each step crosses the internet, so it takes 20 to 30 minutes
(``--small``: a few minutes). Everything is one transaction: stopped half-way, nothing is kept.
See docs/workflows/render-neon-hosting.md.
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
        parser.add_argument(
            "--hosted-development",
            action="store_true",
            help="Fill the hosted Development hospital (synthetic data only), not a PC demo one",
        )

    def handle(self, *args, **opts):
        password = None
        if opts["password_env"]:
            password = os.environ.get(opts["password_env"])
            if not password:
                raise CommandError(f"Environment variable {opts['password_env']} is not set.")
        if opts["hosted_development"]:
            self.stdout.write("Filling the hosted Development hospital: 20 to 30 minutes...")
            self.stdout.flush()
        try:
            ctx = seed_hospital(
                by_key(opts["hospital"]),
                password=password,
                small=opts["small"],
                hosted_development=opts["hosted_development"],
            )
        except (DemoError, KeyError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Filled {ctx.organization.display_name}:"))
        for what, count in ctx.counts.items():
            self.stdout.write(f"  {what}: {count}")
        self.stdout.write("Sign-in accounts (demo password):")
        for email, what in ctx.logins:
            self.stdout.write(f"  {email}  {what}")
        if ctx.examples:
            self.stdout.write("Try these on Patients -> Search (HIMS-PAT-002):")
            for typed, finds in ctx.examples:
                self.stdout.write(f"  {typed}  ->  {finds}")
