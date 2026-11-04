"""Real client address and browser protection headers (HIMS-SEC-012, HIMS-SEC-014)."""

import ast
import json
from pathlib import Path

import pytest
from django.core.cache import cache
from django.test import Client, RequestFactory, override_settings
from rest_framework.test import APIClient

from common.client_ip import client_ip
from common.security_headers import BROWSER_REPORT_PATH, CONSOLE_POLICY

BACKEND = Path(__file__).resolve().parents[2]
PROXIES = ["10.0.0.0/8"]


def _ip(remote="10.0.0.5", forwarded=None):
    extra = {"REMOTE_ADDR": remote}
    if forwarded is not None:
        extra["HTTP_X_FORWARDED_FOR"] = forwarded
    return client_ip(RequestFactory().get("/", **extra))


def test_forwarded_header_is_ignored_when_no_proxies_are_configured():
    assert _ip("203.0.113.9", "198.51.100.1") == "203.0.113.9"


@override_settings(HIMS_TRUSTED_PROXIES=PROXIES)
@pytest.mark.parametrize(
    ("remote", "forwarded", "expected"),
    [
        ("10.0.0.5", "203.0.113.9", "203.0.113.9"),  # through the load balancer
        ("203.0.113.9", "198.51.100.1", "203.0.113.9"),  # not from our proxy: header not believed
        ("10.0.0.5", "198.51.100.1, 203.0.113.9", "203.0.113.9"),  # faked left part is ignored
        ("10.0.0.5", "203.0.113.9, 10.0.0.7", "203.0.113.9"),  # two of our proxies
        ("10.0.0.5", "not-an-address", "10.0.0.5"),
        ("10.0.0.5", "10.0.0.6, 10.0.0.7", "10.0.0.5"),  # only our own proxies
        ("10.0.0.5", None, "10.0.0.5"),
        ("10.0.0.5", "::ffff:203.0.113.9", "203.0.113.9"),
        ("10.0.0.5", "2001:db8::1", "2001:db8::1"),
    ],
)
def test_forwarded_header_is_believed_only_from_our_own_proxies(remote, forwarded, expected):
    assert _ip(remote, forwarded) == expected


@pytest.mark.django_db
def test_faking_the_header_does_not_get_around_the_sign_in_limit():
    cache.clear()
    client = APIClient()
    statuses = []
    for attempt in range(7):  # the test limit is 5 a minute
        response = client.post(
            "/api/v1/auth/login/",
            {"email": "nobody@example.test", "password": "Synthetic-Wrong-Passw0rd-1234"},
            format="json",
            HTTP_X_FORWARDED_FOR=f"198.51.100.{attempt}",
        )
        statuses.append(response.status_code)
    cache.clear()
    assert 429 in statuses


def test_only_client_ip_reads_the_address_headers():
    allowed = {BACKEND / "common" / "client_ip.py"}
    for folder in ("apps", "common", "config"):
        for path in (BACKEND / folder).rglob("*.py"):
            if path in allowed or "tests" in path.parts or "migrations" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and node.value in (
                    "REMOTE_ADDR",
                    "HTTP_X_FORWARDED_FOR",
                ):
                    pytest.fail(f"{path}: use common.client_ip.client_ip")


def test_api_responses_forbid_everything():
    response = Client().get("/health/live/")
    policy = response.headers["Content-Security-Policy"]
    assert policy.startswith("default-src 'none'")
    assert "frame-ancestors 'none'" in policy
    assert "camera=()" in response.headers["Permissions-Policy"]
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "same-origin"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"


@pytest.mark.django_db
def test_admin_console_scripts_are_limited_to_our_own():
    response = Client().get("/admin/login/")
    assert response.headers["Content-Security-Policy"] == CONSOLE_POLICY
    assert "script-src 'self';" in CONSOLE_POLICY


@override_settings(HIMS_CSP_REPORT_ONLY=True)
def test_report_only_switch_reports_instead_of_blocking():
    response = Client().get("/health/live/")
    assert "Content-Security-Policy" not in response.headers
    assert response.headers["Content-Security-Policy-Report-Only"].startswith("default-src")


def test_screens_policy_blocks_foreign_and_inline_scripts_and_reports_here():
    path = BACKEND.parent / "frontend" / "security-headers.json"
    policy = json.loads(path.read_text(encoding="utf-8"))["Content-Security-Policy"]
    directives = dict(part.strip().split(" ", 1) for part in policy.split(";"))
    assert directives["script-src"] == "'self'"
    assert directives["connect-src"] == "'self'"
    assert directives["object-src"] == "'none'"
    assert directives["frame-ancestors"] == "'none'"
    assert directives["report-uri"] == BROWSER_REPORT_PATH
    assert "unsafe-eval" not in policy
