"""The browser-test database reset can never touch a real database (HIMS-QA-001)."""

import pytest
from django.core.management.base import CommandError

from common.devtools.management.commands.reset_e2e_database import check_safe


@pytest.mark.parametrize(
    ("environment", "name"),
    [
        ("production", "hims_e2e"),
        ("staging", "hims_e2e_in"),
        ("development", "hims_e2e"),
        ("local", "hims"),
        ("local", "hims_india"),
        ("test", "regress21"),
    ],
)
def test_refuses_anything_but_a_local_hims_e2e_database(environment, name):
    with pytest.raises(CommandError, match="Refused"):
        check_safe(environment, name)


def test_allows_the_local_browser_test_database():
    check_safe("local", "hims_e2e")
    check_safe("test", "hims_e2e_ci")
