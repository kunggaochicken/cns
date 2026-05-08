from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.telemetry.otel import inject_gigabrain_attrs, setup_otel


def test_inject_gigabrain_attrs_writes_namespace():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer(__name__)

    with tracer.start_as_current_span("test") as span:
        inject_gigabrain_attrs(
            span,
            thought_id="t_1",
            agent_id="engineer-1",
            agent_role="engineer",
            classification="clear",
        )

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    attrs = dict(spans[0].attributes)
    assert attrs["gigabrain.thought_id"] == "t_1"
    assert attrs["gigabrain.agent_id"] == "engineer-1"
    assert attrs["gigabrain.agent_role"] == "engineer"
    assert attrs["gigabrain.classification"] == "clear"


def test_setup_otel_idempotent(tmp_path):
    setup_otel(otlp_endpoint=f"file://{tmp_path}/traces1")
    setup_otel(otlp_endpoint=f"file://{tmp_path}/traces2")
    # Second call must not crash; first-wins semantics
