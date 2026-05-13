import asyncio
import time
from collections.abc import AsyncIterator


class PerPathDebouncer:
    """Coalesces rapid pushes per path; emits each path once after `window_seconds`
    elapse with no further pushes for that path.

    Single-consumer: only one call to `stream()` is supported at a time.
    """

    def __init__(self, window_seconds: float):
        self._window = window_seconds
        self._last: dict[str, float] = {}
        self._wake = asyncio.Event()
        self._closed = False

    def push(self, path: str) -> None:
        self._last[path] = time.monotonic()
        self._wake.set()

    def close(self) -> None:
        self._closed = True
        self._wake.set()

    async def stream(self) -> AsyncIterator[str]:
        while not self._closed or self._last:
            if not self._last:
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=self._window)
                except asyncio.TimeoutError:
                    pass
                continue
            now = time.monotonic()
            ready = [p for p, t in self._last.items() if now - t >= self._window]
            if ready:
                for p in ready:
                    del self._last[p]
                    yield p
                continue
            # Sleep until the oldest entry will be ready (or until a new push arrives).
            soonest = min(self._last.values())
            wait = max(0.0, (soonest + self._window) - now)
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=wait)
            except asyncio.TimeoutError:
                pass
