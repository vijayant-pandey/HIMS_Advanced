"""OpenTelemetry tracing (spec 6 "OpenTelemetry-compatible tracing", 18, 27.2, 29.1;
HIMS-PLAT-016).

Off by default. Switch on per environment with ``HIMS_TRACING_EXPORTER``:

* ``none``    (default) nothing is traced or sent;
* ``console`` spans are printed as JSON lines (developer PC);
* ``otlp``    spans are sent to an OpenTelemetry collector (AWS Distro for OpenTelemetry /
  X-Ray, Jaeger, ...). Endpoint and headers come from the standard ``OTEL_EXPORTER_OTLP_*``
  environment variables.

What is traced: API requests (Django), database queries (psycopg), Celery tasks (sending and
running) and outbound HTTP calls (urllib3, which ``requests`` also uses).

PHI safety (spec 13.3, 27.2): URLs are recorded **without query strings** (search terms such as
a patient's name never reach a trace), SQL is recorded with placeholders only (never the values),
no request or response bodies, headers or user details are recorded. Each API span carries the
request's reference number (``hims.request_id``) so a trace can be found from an error screen,
and every log line written during a traced request carries ``trace_id`` / ``span_id``.
"""

import logging
from urllib.parse import urlsplit, urlunsplit

from django.conf import settings

logger = logging.getLogger(__name__)

EXPORTERS = ("none", "console", "otlp")
# Health checks run every few seconds; tracing them is noise.
EXCLUDED_URLS = "health/"
# Span attributes that may carry a full URL or query string, by semantic-convention version.
_URL_ATTRIBUTES = ("http.url", "url.full")
_TARGET_ATTRIBUTES = ("http.target",)
_QUERY_ATTRIBUTES = ("url.query",)

_configured: set[str] = set()


def strip_query(url: str) -> str:
    """The URL without query string, fragment or credentials."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "[invalid url]"
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def scrub_span(span) -> None:
    """Remove query strings from a span's URL attributes (PHI safety)."""
    if not span.is_recording():
        return
    attributes = getattr(span, "attributes", None) or {}
    for key in _URL_ATTRIBUTES:
        if key in attributes:
            span.set_attribute(key, strip_query(str(attributes[key])))
    for key in _TARGET_ATTRIBUTES:
        if key in attributes:
            span.set_attribute(key, str(attributes[key]).split("?", 1)[0])
    for key in _QUERY_ATTRIBUTES:
        if key in attributes:
            span.set_attribute(key, "[removed]")


def _django_request_hook(span, request) -> None:
    scrub_span(span)


def _django_response_hook(span, request, response) -> None:
    if span.is_recording():
        reference = response.get("X-Request-ID") if hasattr(response, "get") else None
        if reference:
            span.set_attribute("hims.request_id", reference)
        scrub_span(span)


def _http_request_hook(span, *args, **kwargs) -> None:
    scrub_span(span)


def _http_response_hook(span, *args, **kwargs) -> None:
    scrub_span(span)


def build_tracer_provider(exporter: str, *, service_name: str, span_exporter=None):
    """A tracer provider for ``exporter``; ``span_exporter`` overrides it (tests)."""
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": settings.HIMS_RELEASE,
            "deployment.environment.name": settings.HIMS_ENVIRONMENT,
            "hims.deployment_id": settings.HIMS_DEPLOYMENT_ID,
        }
    )
    provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(settings.HIMS_TRACING_SAMPLE_RATIO)),
    )
    if span_exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    elif exporter == "console":
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    elif exporter == "otlp":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    return provider


def instrument(provider, *, django: bool = True) -> None:
    """Switch on the instrumentations with the PHI-safe hooks."""
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
    from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor

    if django:
        from opentelemetry.instrumentation.django import DjangoInstrumentor

        DjangoInstrumentor().instrument(
            tracer_provider=provider,
            request_hook=_django_request_hook,
            response_hook=_django_response_hook,
            excluded_urls=EXCLUDED_URLS,
        )
    PsycopgInstrumentor().instrument(
        tracer_provider=provider, enable_commenter=False, skip_dep_check=True
    )
    CeleryInstrumentor().instrument(tracer_provider=provider)
    URLLib3Instrumentor().instrument(
        tracer_provider=provider,
        request_hook=_http_request_hook,
        response_hook=_http_response_hook,
    )


def uninstrument() -> None:
    """Undo ``instrument`` (tests)."""
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.instrumentation.django import DjangoInstrumentor
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
    from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor

    for instrumentor in (
        DjangoInstrumentor(),
        PsycopgInstrumentor(),
        CeleryInstrumentor(),
        URLLib3Instrumentor(),
    ):
        if instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.uninstrument()


def configure_tracing(service_name: str, *, django: bool = True) -> bool:
    """Set up tracing for this process once. Returns True when tracing is on.

    Call before the WSGI handler loads its middleware (config/wsgi.py) and, for Celery, in each
    worker process after it starts (config/celery.py).
    """
    exporter = settings.HIMS_TRACING_EXPORTER
    if exporter == "none" or service_name in _configured:
        return exporter != "none"
    from opentelemetry import trace

    provider = build_tracer_provider(exporter, service_name=service_name)
    trace.set_tracer_provider(provider)
    instrument(provider, django=django)
    _configured.add(service_name)
    logger.info(
        "tracing_enabled",
        extra={"exporter": exporter, "service": service_name},
    )
    return True


def current_trace_ids() -> dict[str, str]:
    """``trace_id``/``span_id`` of the active span, for log lines (empty when not tracing)."""
    try:
        from opentelemetry import trace
    except ImportError:  # packages not installed yet (e.g. before `pip install` after a pull)
        return {}

    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return {}
    return {"trace_id": f"{context.trace_id:032x}", "span_id": f"{context.span_id:016x}"}
