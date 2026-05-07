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
