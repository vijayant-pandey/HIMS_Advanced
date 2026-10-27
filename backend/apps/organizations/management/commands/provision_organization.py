"""Provision this deployment's hospital organization (spec 7.2, 17.4 step 1).

Run once per customer deployment by provisioning automation (control plane / release job),
after migrations. Creates the organization, the system roles, default numbering schemes, the first
organization administrator and, optionally, the first auditor.

Initial passwords are read from environment variables named on the command line, never from
arguments (which leak into shell history and process listings). Without a password the
account waits for the invitation flow (HIMS-IAM-003).
"""

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.access_control.services import assign_role, create_system_roles
from apps.identity.services import create_user
from apps.numbering.services import ensure_default_schemes
from apps.organizations.models import Country, Currency
from apps.organizations.services import provision_organization


class Command(BaseCommand):
    help = "Create the hospital organization, system roles and first administrator."

    def add_arguments(self, parser):
        parser.add_argument("--legal-name", required=True)
        parser.add_argument("--display-name", required=True)
        parser.add_argument("--country", required=True, choices=Country.values)
        parser.add_argument("--timezone", required=True, help="IANA zone, e.g. Asia/Kolkata")
        parser.add_argument("--currency", required=True, choices=Currency.values)
        parser.add_argument("--admin-email", required=True)
        parser.add_argument("--admin-name", required=True)
        parser.add_argument("--admin-password-env", help="Env var holding the initial password")
        parser.add_argument("--auditor-email")
        parser.add_argument("--auditor-name")
        parser.add_argument("--auditor-password-env")

    def _password(self, env_name: str | None) -> str | None:
        if not env_name:
            return None
        value = os.environ.get(env_name)
        if not value:
            raise CommandError(f"Environment variable {env_name} is not set.")
        return value

    @transaction.atomic
    def handle(self, *args, **opts):
        organization = provision_organization(
            legal_name=opts["legal_name"],
            display_name=opts["display_name"],
            country=opts["country"],
            default_timezone=opts["timezone"],
            default_currency=opts["currency"],
        )
        roles = create_system_roles(organization)
        ensure_default_schemes(organization)

        admin = create_user(
            email=opts["admin_email"],
            display_name=opts["admin_name"],
            password=self._password(opts["admin_password_env"]),
        )
        assign_role(
            actor=None,
            user=admin,
            role=roles["organization-administrator"],
            reason="Initial administrator created at provisioning",
        )

        if opts["auditor_email"]:
            # Separation of duties: the administrator role cannot read or grant audit access.
            auditor = create_user(
                email=opts["auditor_email"],
                display_name=opts["auditor_name"] or opts["auditor_email"],
                password=self._password(opts["auditor_password_env"]),
            )
            assign_role(
                actor=None,
                user=auditor,
                role=roles["auditor"],
                reason="Initial auditor created at provisioning",
            )

        self.stdout.write(self.style.SUCCESS(f"Provisioned {organization.display_name}."))
