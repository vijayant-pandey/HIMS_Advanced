"""Error text in traces gets the same rules as logs (HIMS-SEC-020; spec 13.3, 18, 27.2).
Spans are kept in memory; nothing is sent anywhere. All data is synthetic."""

import json

import pytest
from django.conf import settings
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode

from common import tracing

PATIENT_PHONE = "+919800019052"
EMAIL = "canary.trace@synthetic.test"
LINK = "https://hims.example/activate#token=Synthetic-Link-Passw0rd-1907"


@pytest.fixture
def exported():
    exporter = InMemorySpanExporter()
    provider = tracing.build_tracer_provider(
        "none", service_name="hims-trace-test", span_exporter=exporter
    )
    return exporter, provider.get_tracer("hims.test")


def _text(exporter) -> str:
    return "\n".join(span.to_json() for span in exporter.get_finished_spans())


def test_error_message_stack_and_status_are_filtered(exported):
    exporter, tracer = exported
    error = RuntimeError(
        f"gateway refused to={PATIENT_PHONE} for {EMAIL}, link {LINK}, "
        f"key {settings.SECRET_KEY}, Key (email)=({EMAIL}) already exists"
    )
    with tracer.start_as_current_span("send sms") as span:
        span.record_exception(error)
        span.set_status(Status(StatusCode.ERROR, str(error)))
    text = _text(exporter)
    for secret in (PATIENT_PHONE, EMAIL, "Synthetic-Link-Passw0rd-1907", settings.SECRET_KEY):
        assert secret not in text
    (finished,) = exporter.get_finished_spans()
    (event,) = finished.events
    assert event.name == "exception"
    assert event.attributes["exception.type"] == "RuntimeError"
    assert "gateway refused" in event.attributes["exception.message"]  # the useful part stays
    assert "[hidden]" in event.attributes["exception.message"]
    assert "RuntimeError" in event.attributes["exception.stacktrace"]
    assert finished.status.status_code == StatusCode.ERROR
    assert "[hidden]" in finished.status.description


def test_attributes_are_filtered_by_name_and_value(exported):
    exporter, tracer = exported
    with tracer.start_as_current_span("outside call") as span:
        span.set_attribute("http.request.header.authorization", ("Bearer abcdef123456",))
        span.set_attribute("peer.note", f"called by {EMAIL}")
        span.set_attribute("http.status_code", 502)
        span.set_attribute("retry", True)
    (finished,) = exporter.get_finished_spans()
    attributes = dict(finished.attributes)
    assert attributes["http.request.header.authorization"] == ("[hidden]",)
    assert EMAIL not in json.dumps(attributes)
    assert attributes["http.status_code"] == 502 and attributes["retry"] is True


def test_harmless_spans_keep_what_support_needs(exported):
    exporter, tracer = exported
    with tracer.start_as_current_span("GET api/v1/staff/<uuid:pk>/") as span:
        span.set_attribute("http.route", "api/v1/staff/<uuid:pk>/")
        span.set_attribute("hims.request_id", "3f2a9c1e-0000-4000-8000-000000000001")
    (finished,) = exporter.get_finished_spans()
    assert finished.name == "GET api/v1/staff/<uuid:pk>/"
    assert finished.attributes["hims.request_id"] == "3f2a9c1e-0000-4000-8000-000000000001"
    assert finished.context.trace_id and finished.start_time and finished.end_time


@pytest.mark.parametrize("exporter_name", ["console", "otlp"])
def test_every_way_out_is_filtered(exporter_name):
    provider = tracing.build_tracer_provider(exporter_name, service_name="hims-trace-test")
    processors = provider._active_span_processor._span_processors
    assert processors
    for processor in processors:
        assert isinstance(processor.span_exporter, tracing.ScrubbingSpanExporter)
    provider.shutdown()


def test_record_error_does_nothing_when_not_tracing():
    tracing.record_error(RuntimeError("no span"))  # no exception, nothing to record
