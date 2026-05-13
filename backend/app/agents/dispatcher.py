import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from app.agents.config import DispatchConfig

log = logging.getLogger(__name__)


class Dispatcher:
    """Bounded-concurrency dispatcher for agent runs.

    Two-level concurrency control:
    - A global asyncio.Semaphore caps total concurrent firings (`max_parallel`).
    - A per-role asyncio.Lock serializes firings for the same role, optionally
      tightened further by `per_role[role]` (a per-role semaphore that overrides
      the role lock when set).

    Failure isolation: exceptions raised by `run_fn` are logged and swallowed
    so sibling dispatches finish.
    """

    def __init__(self, *, cfg: DispatchConfig):
        self._cfg = cfg
        self._global_sem = asyncio.Semaphore(cfg.max_parallel)
        self._role_sems: dict[str, asyncio.Semaphore] = {
            role: asyncio.Semaphore(n) for role, n in cfg.per_role.items()
        }
        self._role_locks: dict[str, asyncio.Lock] = {}
        self._inflight: dict[str, dict] = {}

    def _role_gate(self, role: str) -> asyncio.Semaphore | asyncio.Lock:
        if role in self._role_sems:
            return self._role_sems[role]
        lock = self._role_locks.get(role)
        if lock is None:
            lock = asyncio.Lock()
            self._role_locks[role] = lock
        return lock

    def in_flight(self) -> list[dict]:
        """Snapshot of currently-running firings: [{firing_id, role, started_at}]."""
        return [dict(v) for v in self._inflight.values()]

    async def dispatch(
        self,
        *,
        role: str,
        run_fn: Callable[[], Awaitable[None]],
        firing_id: str | None = None,
    ) -> None:
        """Run `run_fn()` under role + global concurrency limits.

        Failures are logged and swallowed so siblings complete.
        """
        fid = firing_id or f"f_{uuid.uuid4().hex[:12]}"
        role_gate = self._role_gate(role)
        async with role_gate:
            async with self._global_sem:
                self._inflight[fid] = {
                    "firing_id": fid,
                    "role": role,
                    "started_at": time.time(),
                }
                try:
                    await run_fn()
                except Exception:
                    log.exception(
                        "Dispatcher: run_fn failed for role=%s firing_id=%s",
                        role,
                        fid,
                    )
                finally:
                    self._inflight.pop(fid, None)
