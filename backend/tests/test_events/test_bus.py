import asyncio

import pytest
from app.events.bus import EventBus
from app.events.schemas import ThoughtCreated


@pytest.mark.asyncio
async def test_publish_subscribe_delivers_event():
    bus = EventBus()
    received: list[ThoughtCreated] = []

    async def handler(event: ThoughtCreated):
        received.append(event)

    bus.subscribe("thought.created", handler)
    await bus.publish(ThoughtCreated(thought_id="t_1", content="hi"))
    await asyncio.sleep(0.05)  # allow handler to run

    assert len(received) == 1
    assert received[0].thought_id == "t_1"


@pytest.mark.asyncio
async def test_multiple_subscribers_all_get_event():
    bus = EventBus()
    counts = {"a": 0, "b": 0}

    async def handler_a(_):
        counts["a"] += 1

    async def handler_b(_):
        counts["b"] += 1

    bus.subscribe("thought.created", handler_a)
    bus.subscribe("thought.created", handler_b)
    await bus.publish(ThoughtCreated(thought_id="t_2", content="hi"))
    await asyncio.sleep(0.05)

    assert counts == {"a": 1, "b": 1}


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe("thought.created", handler)
    await bus.publish(ThoughtCreated(thought_id="t_1", content="hi"))
    await asyncio.sleep(0.05)
    assert len(received) == 1

    bus.unsubscribe("thought.created", handler)
    await bus.publish(ThoughtCreated(thought_id="t_2", content="hi"))
    await asyncio.sleep(0.05)
    assert len(received) == 1  # still 1 — second event not delivered


@pytest.mark.asyncio
async def test_unsubscribe_noop_when_not_subscribed():
    """Calling unsubscribe for a handler that was never registered must not raise."""
    bus = EventBus()

    async def handler(event):
        pass

    # No prior subscribe — must not raise
    bus.unsubscribe("thought.created", handler)
    # Also safe to unsubscribe a handler for an unknown event name
    bus.unsubscribe("nonexistent.event", handler)
