import logging
from pathlib import Path

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.trace import Span

log = logging.getLogger(__name__)
_initialized = False


def setup_otel(*, otlp_endpoint: str, service_name: str = "gigabrain") -> None:
    """Wire OTel exporter. Idempotent — first call wins."""
    global _initialized
    if _initialized:
        return
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if otlp_endpoint.startswith("file://"):
        path = Path(otlp_endpoint.removeprefix("file://"))
        path.parent.mkdir(parents=True, exist_ok=True)
        provider.add_span_processor(
            SimpleSpanProcessor(ConsoleSpanExporter(out=path.open("a")))
        )
    elif otlp_endpoint.startswith(("http://", "https://")):
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        raise ValueError(f"Unsupported otlp_endpoint scheme: {otlp_endpoint}")

    trace.set_tracer_provider(provider)
    _initialized = True


_GB_ATTR_KEYS = {
    "thought_id",
    "firing_id",
    "gate_item_id",
    "agent_id",
    "agent_role",
    "outcome",
    "classification",
}


def inject_gigabrain_attrs(span: Span, **kwargs) -> None:
    """Set the gigabrain.* custom attributes on the current span."""
    for key, value in kwargs.items():
        if value is None:
            continue
        if key not in _GB_ATTR_KEYS:
            log.warning("Unknown gigabrain attr: %s", key)
            continue
        span.set_attribute(f"gigabrain.{key}", value)
