import asyncio

import pytest

from app.api.stream import make_event_generator
from app.events.bus import EventBus
from app.events.schemas import GraphChanged


@pytest.mark.asyncio
async def test_stream_emits_graph_changed_events():
    """
    Verify the SSE generator emits graph.changed events.

    Note: ASGITransport (used in httpx in-process tests) buffers the entire
    ASGI response before surfacing any chunks, making it incompatible with an
    infinite SSE generator (deadlock: generator awaits events, transport awaits
    generator completion).  We therefore test the generator via
    ``make_event_generator`` which is the real implementation used by the route.
    """
    bus = EventBus()
    _queue, generator = make_event_generator(bus)

    async def producer():
        await asyncio.sleep(0.05)
        await bus.publish(GraphChanged(change_type="node_created", node_id="t_1"))

    producer_task = asyncio.create_task(producer())

    # Drain the generator until we see the expected payload.
    chunks: list[str] = []
    async for chunk in generator:
        chunks.append(chunk)
        body = "".join(chunks)
        if "node_created" in body and "t_1" in body:
            break

    await generator.aclose()
    await producer_task

    full = "".join(chunks)
    assert "node_created" in full
    assert "t_1" in full
