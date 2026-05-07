import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.events.bus import EventBus


def make_event_generator(bus: EventBus) -> tuple[asyncio.Queue, object]:
    """
    Subscribe to SSE event topics on *bus* and return ``(queue, generator)``.

    The returned async generator yields SSE-formatted text chunks (keepalive
    comments and ``data:`` lines).  Callers must keep a reference to *queue*
    if they need to inspect or drain it independently.

    Note: ASGITransport (used in httpx in-process tests) buffers the full
    response before surfacing any bytes to the caller, so it cannot be used
    directly with this infinite generator.  Tests should drive the generator
    directly via ``make_event_generator``.
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def handler(event):
        await queue.put(event)

    bus.subscribe("graph.changed", handler)
    bus.subscribe("gate.created", handler)
    bus.subscribe("fire.neuron", handler)

    async def _generator():
        # Send an initial keepalive comment immediately so the HTTP response
        # starts flowing and the event loop can interleave the producer task.
        yield ": keepalive\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                # Yield periodically to keep the connection alive and give
                # the event loop a chance to run other tasks.
                yield ": keepalive\n\n"
                continue
            except asyncio.CancelledError:
                return
            payload = event.model_dump() if hasattr(event, "model_dump") else event
            yield f"data: {json.dumps(payload, default=str)}\n\n"

    return queue, _generator()


def build_stream_router(bus: EventBus) -> APIRouter:
    router = APIRouter()

    @router.get("/stream")
    async def stream():
        _queue, generator = make_event_generator(bus)
        return StreamingResponse(generator, media_type="text/event-stream")

    return router
