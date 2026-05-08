import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[Callable[[Any], Awaitable[None]]]] = {}

    def subscribe(
        self, event_name: str, handler: Callable[[Any], Awaitable[None]]
    ) -> None:
        self._subscribers.setdefault(event_name, []).append(handler)

    async def publish(self, event: Any) -> None:
        name = getattr(event, "event", None)
        if name is None:
            raise ValueError("Event must have `event` field")
        handlers = self._subscribers.get(name, [])
        for h in handlers:
            asyncio.create_task(h(event))
