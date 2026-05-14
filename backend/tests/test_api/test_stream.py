import asyncio

import pytest

from app.api.stream import make_event_generator
from app.events.bus import EventBus
from app.events.schemas import AgentRunCompleted, AgentRunStarted, GraphChanged


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


@pytest.mark.asyncio
async def test_generator_aclose_unsubscribes_handlers():
    """After aclose(), the three handlers must be removed from bus._subscribers.

    The generator must be started (advanced at least once) before aclose() so
    that the try/finally inside the generator body is entered — Python's async
    generator protocol skips the body entirely if the generator was never
    iterated.
    """
    bus = EventBus()
    _queue, generator = make_event_generator(bus)

    # Confirm handlers were subscribed
    assert len(bus._subscribers.get("graph.changed", [])) == 1
    assert len(bus._subscribers.get("gate.created", [])) == 1
    assert len(bus._subscribers.get("fire.neuron", [])) == 1
    assert len(bus._subscribers.get("agent.run.started", [])) == 1
    assert len(bus._subscribers.get("agent.run.completed", [])) == 1

    # Advance past the initial keepalive so the generator body is entered and
    # the try/finally is active.
    first_chunk = await generator.__anext__()
    assert "keepalive" in first_chunk

    await generator.aclose()

    # All five handlers must be gone
    assert len(bus._subscribers.get("graph.changed", [])) == 0
    assert len(bus._subscribers.get("gate.created", [])) == 0
    assert len(bus._subscribers.get("fire.neuron", [])) == 0
    assert len(bus._subscribers.get("agent.run.started", [])) == 0
    assert len(bus._subscribers.get("agent.run.completed", [])) == 0


@pytest.mark.asyncio
async def test_stream_emits_agent_run_events():
    """
    Verify the SSE generator forwards agent.run.started and agent.run.completed
    events so that the brain view can track in-flight agent runs.
    """
    import time

    bus = EventBus()
    _queue, generator = make_event_generator(bus)

    async def producer():
        await asyncio.sleep(0.05)
        await bus.publish(
            AgentRunStarted(
                firing_id="fire-abc",
                role="engineer",
                started_at=time.time(),
            )
        )
        await bus.publish(
            AgentRunCompleted(
                firing_id="fire-abc",
                role="engineer",
                outcome="success",
                duration_seconds=1.23,
            )
        )

    producer_task = asyncio.create_task(producer())

    # Collect chunks until both events have surfaced.
    chunks: list[str] = []
    async for chunk in generator:
        chunks.append(chunk)
        body = "".join(chunks)
        if "agent.run.started" in body and "agent.run.completed" in body:
            break

    await generator.aclose()
    await producer_task

    full = "".join(chunks)
    assert "agent.run.started" in full
    assert "agent.run.completed" in full
    assert "fire-abc" in full
    assert "engineer" in full
