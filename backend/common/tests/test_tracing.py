"""OpenTelemetry tracing (HIMS-PLAT-016): off by default, PHI-safe, linked to reference numbers
and log lines. Spans are collected in memory; nothing is sent anywhere. Synthetic data only."""

import json
import logging

import pytest
from django.test import override_settings
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from common import tracing
from common.logging import JsonFormatter


@pytest.fixture
def spans():
    exporter = InMemorySpanExporter()
    provider = tracing.build_tracer_provider(
        "none", service_name="hims-api-test", span_exporter=exporter
    )
    tracing.instrument(provider)
    try:
        yield exporter, provider
    finally:
        tracing.uninstrument()


def _server_spans(exporter):
    return [s for s in exporter.get_finished_spans() if s.kind.name == "SERVER"]


def test_strip_query_keeps_only_scheme_host_and_path():
    assert (
        tracing.strip_query("https://user:pw@api.example.test:8443/v1/x?name=Asha#top")
        == "https://api.example.test:8443/v1/x"
    )
    assert tracing.strip_query("/api/v1/accounts/?search=Asha") == "/api/v1/accounts/"


def test_tracing_is_off_unless_switched_on():
    assert tracing.configure_tracing("hims-api-off") is False
    assert tracing.current_trace_ids() == {}


@pytest.mark.django_db
def test_api_request_is_traced_without_the_search_words(spans, client_for, admin_user):
    exporter, _ = spans
    response = client_for(admin_user).get("/api/v1/accounts/", {"search": "Asha Nurse"})
    assert response.status_code == 200
    (span,) = _server_spans(exporter)
    attributes = dict(span.attributes)
    assert attributes["hims.request_id"] == response["X-Request-ID"]
    for key in ("http.url", "url.full", "http.target"):
        if key in attributes:
            assert "?" not in attributes[key] and "Asha" not in attributes[key]
    assert attributes.get("url.query", "[removed]") == "[removed]"
    assert "Asha" not in json.dumps(attributes)
    assert span.resource.attributes["service.name"] == "hims-api-test"
    assert span.resource.attributes["hims.deployment_id"] == "test-deployment"


@pytest.mark.django_db
def test_health_checks_are_not_traced(spans, client):
    exporter, _ = spans
    assert client.get("/health/live/").status_code == 200
    assert _server_spans(exporter) == []


def test_outbound_http_spans_lose_query_strings(spans):
    _, provider = spans
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("GET") as span:
        span.set_attribute("http.url", "https://payer.example.test/eligibility?member=ABC123")
        span.set_attribute("url.full", "https://payer.example.test/eligibility?member=ABC123")
        tracing._http_request_hook(span, None)
        assert span.attributes["http.url"] == "https://payer.example.test/eligibility"
        assert span.attributes["url.full"] == "https://payer.example.test/eligibility"


def test_log_lines_carry_the_trace_id(spans):
    _, provider = spans
    formatter = JsonFormatter()
    record = logging.makeLogRecord({"msg": "hello", "levelname": "INFO", "name": "t"})
    assert "trace_id" not in json.loads(formatter.format(record))
    with provider.get_tracer("test").start_as_current_span("work") as span:
        line = json.loads(formatter.format(record))
        assert line["trace_id"] == f"{span.get_span_context().trace_id:032x}"
        assert line["span_id"] == f"{span.get_span_context().span_id:016x}"


def test_sampling_ratio_is_respected(spans):
    with override_settings(HIMS_TRACING_SAMPLE_RATIO=0.0):
        exporter = InMemorySpanExporter()
        provider = tracing.build_tracer_provider(
            "none", service_name="sampled-out", span_exporter=exporter
        )
        with provider.get_tracer("test").start_as_current_span("dropped"):
            pass
        assert exporter.get_finished_spans() == ()


def test_console_exporter_is_selectable():
    provider = tracing.build_tracer_provider("console", service_name="hims-console-test")
    assert provider.resource.attributes["service.name"] == "hims-console-test"
    provider.shutdown()


def test_api_access_log_never_contains_query_strings():
    from pathlib import Path

    settings_file = Path(__file__).resolve().parents[2] / "config" / "gunicorn_conf.py"
    values = {}
    exec(settings_file.read_text(encoding="utf-8"), values)  # noqa: S102 - our own config file
    log_format = values["access_log_format"]
    assert "%(U)s" in log_format  # path only
    for leaky in ("%(r)s", "%(q)s", "%(f)s", "%(a)s"):  # request line, query, referer, browser
        assert leaky not in log_format
