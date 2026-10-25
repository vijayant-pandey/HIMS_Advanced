from django.conf import settings

from common.exceptions import DomainError

from .models import Organization


class DeploymentNotProvisioned(DomainError):
    status_code = 503
    code = "DEPLOYMENT_NOT_PROVISIONED"
    title = "Service not provisioned"


def get_deployment_organization() -> Organization:
    """Return this deployment's organization, verifying it matches the configured identity.

    The organization is resolved from server configuration, never from client input
    (spec 7.4).
    """
    try:
        return Organization.objects.get(deployment_id=settings.HIMS_DEPLOYMENT_ID)
    except Organization.DoesNotExist:
        raise DeploymentNotProvisioned(
            "This deployment has not been provisioned with its hospital organization."
        ) from None
