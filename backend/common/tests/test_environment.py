import pytest
from django.core.exceptions import ImproperlyConfigured

from common.environment import validate_environment


def _validate(**overrides):
    params = {
        "settings_profile": "production",
        "environment": "staging",
        "deployment_id": "customer-a",
        "database_host": "customer-a-staging.cluster.internal",
        "database_environment": "staging",
        "debug": False,
    }
    params.update(overrides)
    validate_environment(**params)


def test_valid_managed_configuration_passes():
    _validate()


def test_database_secret_for_another_environment_is_refused():
    with pytest.raises(ImproperlyConfigured, match="must match"):
        _validate(environment="staging", database_environment="production")


def test_local_process_cannot_reach_remote_database():
    with pytest.raises(ImproperlyConfigured, match="local database"):
        _validate(
            settings_profile="local",
            environment="local",
            database_host="customer-a-prod.cluster.internal",
        )


def test_local_settings_cannot_claim_managed_environment():
    with pytest.raises(ImproperlyConfigured, match="cannot run"):
        _validate(settings_profile="local", environment="production", database_host="localhost")


def test_debug_refused_in_managed_environment():
    with pytest.raises(ImproperlyConfigured, match="DEBUG"):
        _validate(debug=True)


def test_deployment_identity_required():
    with pytest.raises(ImproperlyConfigured, match="HIMS_DEPLOYMENT_ID"):
        _validate(deployment_id="")
