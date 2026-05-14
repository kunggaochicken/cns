# GigaBrain CNS v2 Plan 07 — Parallel Agent Dispatch

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded-concurrency dispatch to the v2 agent runtime so multiple `fire.neuron` events can be processed in parallel without two firings for the same role racing, without failures poisoning siblings, and with structured `agent.run.started` / `agent.run.completed` events for the brain view's SSE stream.

**Architecture:** A new `Dispatcher` primitive sits between `AgentWorker._handle_fire_neuron` and `AgentRuntime.run`. It owns a global `asyncio.Semaphore(max_parallel)` for total concurrency and a `dict[role, asyncio.Lock]` for per-role serialization. Failure isolation is preserved by `try/except` per firing. Two new event types (`agent.run.started`, `agent.run.completed`) flow through the existing `EventBus`/SSE pipeline. Config is loaded from `agents.yaml`'s new top-level `dispatch:` block; current behavior (`max_parallel: 1`) is the default, so nothing breaks for existing deployments.

**Tech Stack:** Python 3.11+ async; `pydantic` for config; `pytest-asyncio` for tests; existing `EventBus`, `AgentRuntime`, `AgentWorker`, `KuzuConnection`, `NodeRepository`, `EdgeRepository`.

---

## Scope: 1 PR, 7 tasks

This plan ships a single PR that:

1. Adds a `DispatchConfig` schema.
2. Adds a `Dispatcher` primitive.
3. Adds two new event types.
4. Refactors `AgentWorker` to dispatch via the primitive.
5. Exposes in-flight state via `/agents/inflight`.
6. Updates `agents.yaml.example` and `docs/self-hosting.md`.
7. Adds an end-to-end concurrency test.

Total LOC estimate: ~250 source + ~300 tests.

## File structure

**Create:**
- `backend/app/agents/dispatcher.py` — the bounded-concurrency primitive
- `backend/tests/test_agents/test_dispatcher.py` — unit tests for the primitive
- `backend/tests/test_agents/test_worker_parallel.py` — concurrency tests through the worker

**Modify:**
- `backend/app/agents/config.py` — add `DispatchConfig` + extend `FleetConfig`
- `backend/app/agents/worker.py` — route firings through the dispatcher
- `backend/app/events/schemas.py` — add `AgentRunStarted` + `AgentRunCompleted`
- `backend/app/agents/api.py` — add `GET /agents/inflight`
- `backend/agents.yaml.example` — add commented `dispatch:` block
- `backend/tests/test_agents/test_config.py` — new tests for `DispatchConfig` parsing
- `backend/tests/test_agents/test_api.py` — new test for `/agents/inflight`
- `docs/self-hosting.md` — add a "Parallel dispatch" section

---

## Task 1: `DispatchConfig` schema + `FleetConfig.dispatch`

**Files:**
- Modify: `backend/app/agents/config.py`
- Test: `backend/tests/test_agents/test_config.py`

The schema lives next to `AgentSpec` because it's loaded from the same `agents.yaml` file. Default `max_parallel: 1` means existing deployments keep their current effective sequential behavior. `per_role` overrides apply on top of the global cap.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_agents/test_config.py`:

```python
def test_fleet_config_defaults_dispatch_max_parallel_to_one(tmp_path):
    p = tmp_path / "f.yaml"
    p.write_text("agents: []\n")
    fleet = load_fleet_config(p)
    assert fleet.dispatch.max_parallel == 1
    assert fleet.dispatch.per_role == {}


def test_fleet_config_parses_dispatch_block(tmp_path):
    p = tmp_path / "f.yaml"
    p.write_text(
        "agents: []\n"
        "dispatch:\n"
        "  max_parallel: 3\n"
        "  per_role:\n"
        "    cto: 1\n"
        "    engineer: 2\n"
    )
    fleet = load_fleet_config(p)
    assert fleet.dispatch.max_parallel == 3
    assert fleet.dispatch.per_role == {"cto": 1, "engineer": 2}


def test_fleet_config_rejects_max_parallel_below_one(tmp_path):
    p = tmp_path / "f.yaml"
    p.write_text("agents: []\ndispatch:\n  max_parallel: 0\n")
    with pytest.raises(ValidationError):
        load_fleet_config(p)


def test_fleet_config_rejects_per_role_value_below_one(tmp_path):
    p = tmp_path / "f.yaml"
    p.write_text(
        "agents: []\ndispatch:\n  max_parallel: 3\n  per_role:\n    cto: 0\n"
    )
    with pytest.raises(ValidationError):
        load_fleet_config(p)
```

Add to imports at top of file: `from pydantic import ValidationError`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_agents/test_config.py -v`
Expected: 4 new tests FAIL with `AttributeError: 'FleetConfig' object has no attribute 'dispatch'` (or KeyError on parse).

- [ ] **Step 3: Implement `DispatchConfig`**

Modify `backend/app/agents/config.py`. Add after `AgentSpec`:

```python
class DispatchConfig(BaseModel):
    """Bounded-concurrency settings for AgentWorker dispatch."""

    max_parallel: int = 1
    per_role: dict[str, int] = {}

    @model_validator(mode="after")
    def _check_positive(self):
        if self.max_parallel < 1:
            raise ValueError("dispatch.max_parallel must be >= 1")
        for role, n in self.per_role.items():
            if n < 1:
                raise ValueError(
                    f"dispatch.per_role[{role!r}] must be >= 1, got {n}"
                )
        return self
```

Extend `FleetConfig` to include `dispatch`:

```python
class FleetConfig(BaseModel):
    agents: list[AgentSpec] = []
    dispatch: DispatchConfig = DispatchConfig()

    @model_validator(mode="after")
    def _check_unique_ids(self):
        seen: set[str] = set()
        for a in self.agents:
            if a.id in seen:
                raise ValueError(f"duplicate agent id: {a.id}")
            seen.add(a.id)
        return self
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_agents/test_config.py -v`
Expected: All tests PASS (including the 4 new ones).

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/config.py backend/tests/test_agents/test_config.py
git commit -m "feat(agents): add DispatchConfig schema for parallel dispatch (Plan 07 task 1)"
```

---

## Task 2: `Dispatcher` primitive

**Files:**
- Create: `backend/app/agents/dispatcher.py`
- Test: `backend/tests/test_agents/test_dispatcher.py`

The primitive is the load-bearing piece. It exposes one method: `dispatch(role, run_fn)`. It serializes per role, caps total concurrency, isolates failures, and exposes in-flight state.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_agents/test_dispatcher.py`:

```python
import asyncio

import pytest

from app.agents.config import DispatchConfig
from app.agents.dispatcher import Dispatcher


@pytest.mark.asyncio
async def test_dispatcher_serializes_same_role():
    """Two firings for the same role must not run concurrently."""
    cfg = DispatchConfig(max_parallel=4)
    disp = Dispatcher(cfg=cfg)
    in_flight = 0
    max_seen = 0

    async def slow():
        nonlocal in_flight, max_seen
        in_flight += 1
        max_seen = max(max_seen, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1

    await asyncio.gather(
        disp.dispatch(role="cto", run_fn=slow),
        disp.dispatch(role="cto", run_fn=slow),
    )
    assert max_seen == 1


@pytest.mark.asyncio
async def test_dispatcher_runs_different_roles_concurrently():
    """Firings for distinct roles run in parallel up to max_parallel."""
    cfg = DispatchConfig(max_parallel=3)
    disp = Dispatcher(cfg=cfg)
    in_flight = 0
    max_seen = 0

    async def slow():
        nonlocal in_flight, max_seen
        in_flight += 1
        max_seen = max(max_seen, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1

    await asyncio.gather(
        disp.dispatch(role="cto", run_fn=slow),
        disp.dispatch(role="engineer", run_fn=slow),
        disp.dispatch(role="pm", run_fn=slow),
    )
    assert max_seen == 3


@pytest.mark.asyncio
async def test_dispatcher_respects_global_cap():
    """With max_parallel=2 and 4 distinct-role firings, only 2 run at a time."""
    cfg = DispatchConfig(max_parallel=2)
    disp = Dispatcher(cfg=cfg)
    in_flight = 0
    max_seen = 0

    async def slow():
        nonlocal in_flight, max_seen
        in_flight += 1
        max_seen = max(max_seen, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1

    await asyncio.gather(
        disp.dispatch(role="a", run_fn=slow),
        disp.dispatch(role="b", run_fn=slow),
        disp.dispatch(role="c", run_fn=slow),
        disp.dispatch(role="d", run_fn=slow),
    )
    assert max_seen == 2


@pytest.mark.asyncio
async def test_dispatcher_failure_isolated():
    """One firing raising must not abort siblings."""
    cfg = DispatchConfig(max_parallel=3)
    disp = Dispatcher(cfg=cfg)
    survivors = 0

    async def boom():
        raise RuntimeError("simulated")

    async def ok():
        nonlocal survivors
        await asyncio.sleep(0.01)
        survivors += 1

    results = await asyncio.gather(
        disp.dispatch(role="a", run_fn=boom),
        disp.dispatch(role="b", run_fn=ok),
        disp.dispatch(role="c", run_fn=ok),
        return_exceptions=True,
    )
    assert survivors == 2
    # The dispatcher swallows the exception (logs it) so dispatch returns None
    assert all(r is None for r in results)


@pytest.mark.asyncio
async def test_dispatcher_per_role_override_below_global():
    """per_role[role] = 1 forces serialization even when global cap allows more."""
    cfg = DispatchConfig(max_parallel=4, per_role={"cto": 1})
    disp = Dispatcher(cfg=cfg)
    in_flight_cto = 0
    max_cto = 0

    async def slow_cto():
        nonlocal in_flight_cto, max_cto
        in_flight_cto += 1
        max_cto = max(max_cto, in_flight_cto)
        await asyncio.sleep(0.03)
        in_flight_cto -= 1

    await asyncio.gather(
        disp.dispatch(role="cto", run_fn=slow_cto),
        disp.dispatch(role="cto", run_fn=slow_cto),
        disp.dispatch(role="cto", run_fn=slow_cto),
    )
    assert max_cto == 1


@pytest.mark.asyncio
async def test_dispatcher_inflight_exposes_running_firings():
    """While a run_fn is in-flight, dispatcher.in_flight() returns its (role, started_at)."""
    cfg = DispatchConfig(max_parallel=2)
    disp = Dispatcher(cfg=cfg)
    started = asyncio.Event()
    release = asyncio.Event()

    async def gated():
        started.set()
        await release.wait()

    task = asyncio.create_task(disp.dispatch(role="cto", run_fn=gated))
    await started.wait()
    snapshot = disp.in_flight()
    assert len(snapshot) == 1
    assert snapshot[0]["role"] == "cto"
    assert isinstance(snapshot[0]["started_at"], float)
    release.set()
    await task
    assert disp.in_flight() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_agents/test_dispatcher.py -v`
Expected: All 6 tests FAIL with `ModuleNotFoundError: No module named 'app.agents.dispatcher'`.

- [ ] **Step 3: Implement the dispatcher**

Create `backend/app/agents/dispatcher.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_agents/test_dispatcher.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/dispatcher.py backend/tests/test_agents/test_dispatcher.py
git commit -m "feat(agents): add Dispatcher primitive for bounded parallel runs (Plan 07 task 2)"
```

---

## Task 3: `AgentRunStarted` and `AgentRunCompleted` events

**Files:**
- Modify: `backend/app/events/schemas.py`
- Test: extend `backend/tests/test_agents/test_dispatcher.py` (no separate file)

Structured events let the brain view's SSE stream show "agent X firing now" / "agent X done" without polling the graph. Each event carries `firing_id` so consumers can correlate.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_agents/test_dispatcher.py`:

```python
from app.events.bus import EventBus
from app.events.schemas import AgentRunCompleted, AgentRunStarted


@pytest.mark.asyncio
async def test_dispatcher_emits_started_and_completed_events():
    cfg = DispatchConfig(max_parallel=2)
    bus = EventBus()
    disp = Dispatcher(cfg=cfg, bus=bus)
    seen: list = []

    async def on_started(e: AgentRunStarted):
        seen.append(("started", e.firing_id, e.role))

    async def on_completed(e: AgentRunCompleted):
        seen.append(("completed", e.firing_id, e.role, e.outcome))

    bus.subscribe("agent.run.started", on_started)
    bus.subscribe("agent.run.completed", on_completed)

    async def ok():
        await asyncio.sleep(0)

    await disp.dispatch(role="engineer", run_fn=ok, firing_id="fid-A")
    await asyncio.sleep(0.01)  # let bus tasks drain

    assert ("started", "fid-A", "engineer") in seen
    assert any(
        s == ("completed", "fid-A", "engineer", "success") for s in seen
    )


@pytest.mark.asyncio
async def test_dispatcher_emits_completed_with_failed_outcome_on_exception():
    cfg = DispatchConfig(max_parallel=2)
    bus = EventBus()
    disp = Dispatcher(cfg=cfg, bus=bus)
    outcomes: list = []

    async def on_completed(e: AgentRunCompleted):
        outcomes.append(e.outcome)

    bus.subscribe("agent.run.completed", on_completed)

    async def boom():
        raise RuntimeError("x")

    await disp.dispatch(role="cto", run_fn=boom, firing_id="fid-B")
    await asyncio.sleep(0.01)

    assert outcomes == ["failed"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_agents/test_dispatcher.py::test_dispatcher_emits_started_and_completed_events tests/test_agents/test_dispatcher.py::test_dispatcher_emits_completed_with_failed_outcome_on_exception -v`
Expected: FAIL — `ImportError: cannot import name 'AgentRunStarted'` and/or `TypeError: Dispatcher.__init__() got an unexpected keyword argument 'bus'`.

- [ ] **Step 3: Add the events and wire the bus into `Dispatcher`**

Modify `backend/app/events/schemas.py`. Append:

```python
class AgentRunStarted(BaseModel):
    event: Literal["agent.run.started"] = "agent.run.started"
    firing_id: str
    role: str
    started_at: float


class AgentRunCompleted(BaseModel):
    event: Literal["agent.run.completed"] = "agent.run.completed"
    firing_id: str
    role: str
    outcome: Literal["success", "failed"]
    duration_seconds: float
```

Modify `backend/app/agents/dispatcher.py`. Add `bus: EventBus | None = None` to `__init__`; emit events around `run_fn`:

```python
import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from app.agents.config import DispatchConfig
from app.events.bus import EventBus
from app.events.schemas import AgentRunCompleted, AgentRunStarted

log = logging.getLogger(__name__)


class Dispatcher:
    def __init__(self, *, cfg: DispatchConfig, bus: EventBus | None = None):
        self._cfg = cfg
        self._bus = bus
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
        return [dict(v) for v in self._inflight.values()]

    async def dispatch(
        self,
        *,
        role: str,
        run_fn: Callable[[], Awaitable[None]],
        firing_id: str | None = None,
    ) -> None:
        fid = firing_id or f"f_{uuid.uuid4().hex[:12]}"
        role_gate = self._role_gate(role)
        async with role_gate:
            async with self._global_sem:
                started_at = time.time()
                self._inflight[fid] = {
                    "firing_id": fid,
                    "role": role,
                    "started_at": started_at,
                }
                if self._bus is not None:
                    await self._bus.publish(
                        AgentRunStarted(
                            firing_id=fid, role=role, started_at=started_at
                        )
                    )
                outcome: str = "success"
                try:
                    await run_fn()
                except Exception:
                    outcome = "failed"
                    log.exception(
                        "Dispatcher: run_fn failed for role=%s firing_id=%s",
                        role,
                        fid,
                    )
                finally:
                    duration = time.time() - started_at
                    self._inflight.pop(fid, None)
                    if self._bus is not None:
                        await self._bus.publish(
                            AgentRunCompleted(
                                firing_id=fid,
                                role=role,
                                outcome=outcome,
                                duration_seconds=duration,
                            )
                        )
```

- [ ] **Step 4: Run all dispatcher tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_agents/test_dispatcher.py -v`
Expected: All 8 tests PASS (6 original + 2 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/events/schemas.py backend/app/agents/dispatcher.py backend/tests/test_agents/test_dispatcher.py
git commit -m "feat(events): AgentRunStarted/Completed events emitted by Dispatcher (Plan 07 task 3)"
```

---

## Task 4: Wire `AgentWorker` to use `Dispatcher`

**Files:**
- Modify: `backend/app/agents/worker.py`
- Modify: `backend/app/main.py` — construct `Dispatcher` and pass it to `AgentWorker`
- Test: Create `backend/tests/test_agents/test_worker_parallel.py`

The worker's existing `_handle_fire_neuron` body is split: the graph bookkeeping (create firing node, edges, mark complete) stays in the worker, but the actual `AgentRuntime.run` call goes inside a `run_fn` passed to `dispatcher.dispatch(role=..., run_fn=...)`. Existing worker tests must continue to pass with `max_parallel=1` (default).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_agents/test_worker_parallel.py`:

```python
import asyncio
from pathlib import Path

import pytest

from app.agents.config import AgentSpec, DispatchConfig, FleetConfig
from app.agents.dispatcher import Dispatcher
from app.agents.registry import AgentRegistry
from app.agents.runtime import AgentRunResult
from app.agents.worker import AgentWorker
from app.config import LLMConfig
from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import ThoughtNode
from app.events.bus import EventBus
from app.events.schemas import FireNeuron


@pytest.fixture
def stack(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    edges = EdgeRepository(conn)
    bus = EventBus()
    yield {
        "conn": conn,
        "nodes": nodes,
        "edges": edges,
        "bus": bus,
        "vault": str(tmp_path / "vault"),
        "repo": None,
    }
    conn.close()


@pytest.mark.asyncio
async def test_worker_runs_distinct_roles_concurrently(stack, monkeypatch):
    """With max_parallel=3, three firings for three roles overlap."""
    reg = AgentRegistry(nodes=stack["nodes"], conn=stack["conn"])
    specs = [
        AgentSpec(id="cto-1", role="cto", persona="x"),
        AgentSpec(id="eng-1", role="engineer", persona="x"),
        AgentSpec(id="pm-1", role="pm", persona="x"),
    ]
    reg.sync(FleetConfig(agents=specs))

    in_flight = 0
    max_seen = 0

    def fake_init(self, *, spec, llm_cfg, vault_path, repo_path):
        self.spec = spec

    async def slow_run(self, *, firing_id, task_summary):
        nonlocal in_flight, max_seen
        in_flight += 1
        max_seen = max(max_seen, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        return AgentRunResult(summary="ok")

    monkeypatch.setattr("app.agents.runtime.AgentRuntime.__init__", fake_init)
    monkeypatch.setattr("app.agents.runtime.AgentRuntime.run", slow_run)

    fleet = FleetConfig(agents=specs, dispatch=DispatchConfig(max_parallel=3))
    dispatcher = Dispatcher(cfg=fleet.dispatch, bus=stack["bus"])
    worker = AgentWorker(
        registry=reg,
        nodes=stack["nodes"],
        edges=stack["edges"],
        bus=stack["bus"],
        llm_cfg=LLMConfig(provider="anthropic", model="x", api_key_env="X"),
        fleet=fleet,
        vault_path=stack["vault"],
        repo_path=stack["repo"],
        dispatcher=dispatcher,
    )
    worker.attach()

    thoughts = []
    for i in range(3):
        t = ThoughtNode(content=f"t{i}", source="cli")
        stack["nodes"].create(t)
        thoughts.append(t)

    await asyncio.gather(
        stack["bus"].publish(FireNeuron(thought_id=thoughts[0].id, agent_role="cto", task_summary="x")),
        stack["bus"].publish(FireNeuron(thought_id=thoughts[1].id, agent_role="engineer", task_summary="x")),
        stack["bus"].publish(FireNeuron(thought_id=thoughts[2].id, agent_role="pm", task_summary="x")),
    )
    await asyncio.sleep(0.2)

    assert max_seen == 3
    firings = stack["conn"].query(
        "MATCH (f:AgentFiring) RETURN f.outcome AS outcome"
    )
    assert len(firings) == 3
    assert all(f["outcome"] == "success" for f in firings)


@pytest.mark.asyncio
async def test_worker_serializes_same_role(stack, monkeypatch):
    """Two firings for the same role do not overlap, even with max_parallel=3."""
    reg = AgentRegistry(nodes=stack["nodes"], conn=stack["conn"])
    spec = AgentSpec(id="cto-1", role="cto", persona="x")
    reg.sync(FleetConfig(agents=[spec]))

    in_flight = 0
    max_seen = 0

    def fake_init(self, *, spec, llm_cfg, vault_path, repo_path):
        self.spec = spec

    async def slow_run(self, *, firing_id, task_summary):
        nonlocal in_flight, max_seen
        in_flight += 1
        max_seen = max(max_seen, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        return AgentRunResult(summary="ok")

    monkeypatch.setattr("app.agents.runtime.AgentRuntime.__init__", fake_init)
    monkeypatch.setattr("app.agents.runtime.AgentRuntime.run", slow_run)

    fleet = FleetConfig(agents=[spec], dispatch=DispatchConfig(max_parallel=3))
    dispatcher = Dispatcher(cfg=fleet.dispatch, bus=stack["bus"])
    worker = AgentWorker(
        registry=reg,
        nodes=stack["nodes"],
        edges=stack["edges"],
        bus=stack["bus"],
        llm_cfg=LLMConfig(provider="anthropic", model="x", api_key_env="X"),
        fleet=fleet,
        vault_path=stack["vault"],
        repo_path=stack["repo"],
        dispatcher=dispatcher,
    )
    worker.attach()

    t1 = ThoughtNode(content="t1", source="cli")
    t2 = ThoughtNode(content="t2", source="cli")
    stack["nodes"].create(t1)
    stack["nodes"].create(t2)

    await asyncio.gather(
        stack["bus"].publish(FireNeuron(thought_id=t1.id, agent_role="cto", task_summary="x")),
        stack["bus"].publish(FireNeuron(thought_id=t2.id, agent_role="cto", task_summary="x")),
    )
    await asyncio.sleep(0.2)

    assert max_seen == 1


@pytest.mark.asyncio
async def test_worker_failure_does_not_poison_siblings(stack, monkeypatch):
    """One firing failing must not abort other in-flight firings."""
    reg = AgentRegistry(nodes=stack["nodes"], conn=stack["conn"])
    specs = [
        AgentSpec(id="cto-1", role="cto", persona="x"),
        AgentSpec(id="eng-1", role="engineer", persona="x"),
    ]
    reg.sync(FleetConfig(agents=specs))

    def fake_init(self, *, spec, llm_cfg, vault_path, repo_path):
        self.spec = spec

    async def maybe_boom(self, *, firing_id, task_summary):
        if self.spec.role == "cto":
            raise RuntimeError("simulated cto crash")
        return AgentRunResult(summary="ok")

    monkeypatch.setattr("app.agents.runtime.AgentRuntime.__init__", fake_init)
    monkeypatch.setattr("app.agents.runtime.AgentRuntime.run", maybe_boom)

    fleet = FleetConfig(agents=specs, dispatch=DispatchConfig(max_parallel=2))
    dispatcher = Dispatcher(cfg=fleet.dispatch, bus=stack["bus"])
    worker = AgentWorker(
        registry=reg,
        nodes=stack["nodes"],
        edges=stack["edges"],
        bus=stack["bus"],
        llm_cfg=LLMConfig(provider="anthropic", model="x", api_key_env="X"),
        fleet=fleet,
        vault_path=stack["vault"],
        repo_path=stack["repo"],
        dispatcher=dispatcher,
    )
    worker.attach()

    t1 = ThoughtNode(content="t1", source="cli")
    t2 = ThoughtNode(content="t2", source="cli")
    stack["nodes"].create(t1)
    stack["nodes"].create(t2)

    await asyncio.gather(
        stack["bus"].publish(FireNeuron(thought_id=t1.id, agent_role="cto", task_summary="x")),
        stack["bus"].publish(FireNeuron(thought_id=t2.id, agent_role="engineer", task_summary="x")),
    )
    await asyncio.sleep(0.2)

    firings = stack["conn"].query(
        "MATCH (f:AgentFiring) RETURN f.agent_id AS agent_id, f.outcome AS outcome"
    )
    by_agent = {f["agent_id"]: f["outcome"] for f in firings}
    assert by_agent == {"cto-1": "failed", "eng-1": "success"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_agents/test_worker_parallel.py -v`
Expected: FAIL — `TypeError: AgentWorker.__init__() got an unexpected keyword argument 'dispatcher'`.

- [ ] **Step 3: Refactor `AgentWorker` to use `Dispatcher`**

Modify `backend/app/agents/worker.py` to accept a `Dispatcher` and route the LLM call through it:

```python
import logging
from datetime import datetime, timezone

from opentelemetry import trace

from app.agents.config import FleetConfig
from app.agents.dispatcher import Dispatcher
from app.agents.registry import AgentRegistry
from app.agents.runtime import AgentRuntime
from app.config import LLMConfig
from app.db.edges import EdgeRepository
from app.db.nodes import NodeRepository
from app.db.schemas import AgentFiringNode, EdgeRecord, NodeType
from app.events.bus import EventBus
from app.events.schemas import FireNeuron
from app.telemetry.otel import inject_gigabrain_attrs

log = logging.getLogger(__name__)


class AgentWorker:
    def __init__(
        self,
        *,
        registry: AgentRegistry,
        nodes: NodeRepository,
        edges: EdgeRepository,
        bus: EventBus,
        llm_cfg: LLMConfig,
        fleet: FleetConfig,
        vault_path: str,
        repo_path: str | None,
        dispatcher: Dispatcher,
    ):
        self.registry = registry
        self.nodes = nodes
        self.edges = edges
        self.bus = bus
        self.llm_cfg = llm_cfg
        self.fleet = fleet
        self.vault_path = vault_path
        self.repo_path = repo_path
        self.dispatcher = dispatcher

    def attach(self) -> None:
        self.bus.subscribe("fire.neuron", self._handle_fire_neuron)

    def _mark_firing_complete(self, firing_id: str, outcome: str) -> None:
        self.nodes.conn.query(
            "MATCH (f:AgentFiring) WHERE f.id = $id "
            "SET f.outcome = $outcome, f.completed_at = $completed_at",
            {
                "id": firing_id,
                "outcome": outcome,
                "completed_at": datetime.now(timezone.utc),
            },
        )

    async def _handle_fire_neuron(self, event: FireNeuron) -> None:
        tracer = trace.get_tracer("gigabrain.agents.worker")
        with tracer.start_as_current_span("agent.run") as span:
            inject_gigabrain_attrs(
                span,
                thought_id=event.thought_id,
                agent_role=event.agent_role,
            )
            agents = self.registry.get_by_role(event.agent_role)
            enabled = [
                a for a in agents if a.get("enabled") and a.get("state") != "paused"
            ]
            if not enabled:
                log.warning(
                    "No enabled agents for role %s; dropping firing for thought %s",
                    event.agent_role,
                    event.thought_id,
                )
                return
            agent_row = enabled[0]
            agent_id = agent_row["id"]

            spec = next((s for s in self.fleet.agents if s.id == agent_id), None)
            if spec is None:
                log.warning(
                    "Agent %s in graph but not in fleet config; dropping",
                    agent_id,
                )
                return

            inject_gigabrain_attrs(span, agent_id=agent_id)

            firing = AgentFiringNode(
                agent_id=agent_id,
                trace_id=f"trace_{event.thought_id}",
            )
            self.nodes.create(firing)
            inject_gigabrain_attrs(span, firing_id=firing.id)

            self.edges.create(
                EdgeRecord(
                    from_id=agent_id,
                    from_type=NodeType.AGENT,
                    to_id=firing.id,
                    to_type=NodeType.AGENT_FIRING,
                    edge_type="produced",
                    confidence=1.0,
                )
            )
            self.edges.create(
                EdgeRecord(
                    from_id=firing.id,
                    from_type=NodeType.AGENT_FIRING,
                    to_id=event.thought_id,
                    to_type=NodeType.THOUGHT,
                    edge_type="fired-from",
                    confidence=1.0,
                )
            )

            async def _run() -> None:
                runtime = AgentRuntime(
                    spec=spec,
                    llm_cfg=self.llm_cfg,
                    vault_path=self.vault_path,
                    repo_path=self.repo_path,
                )
                outcome = "success"
                try:
                    await runtime.run(
                        firing_id=firing.id,
                        task_summary=event.task_summary,
                    )
                except Exception:
                    log.exception("Agent run failed for firing %s", firing.id)
                    outcome = "failed"
                inject_gigabrain_attrs(span, outcome=outcome)
                self._mark_firing_complete(firing.id, outcome)

            await self.dispatcher.dispatch(
                role=event.agent_role,
                run_fn=_run,
                firing_id=firing.id,
            )
```

Note: the dispatcher's outer try/except is redundant with `_run`'s inner try/except — that's intentional. `_run` translates agent failures into a graph `outcome="failed"`; the dispatcher's catch is only for bugs in the bookkeeping path itself.

- [ ] **Step 4: Wire `Dispatcher` into `main.py` lifespan**

Modify `backend/app/main.py`. Replace the current `AgentWorker` construction with:

```python
from app.agents.dispatcher import Dispatcher

dispatcher = Dispatcher(cfg=fleet.dispatch, bus=bus)
worker = AgentWorker(
    registry=registry,
    nodes=nodes,
    edges=edges,
    bus=bus,
    llm_cfg=cfg.llm,
    fleet=fleet,
    vault_path=cfg.agents.vault_path,
    repo_path=cfg.agents.repo_path,
    dispatcher=dispatcher,
)
worker.attach()
app.state.dispatcher = dispatcher
app.state.registry = registry
app.state.worker = worker
app.state.fleet = fleet
```

- [ ] **Step 5: Update the existing worker tests to pass a dispatcher**

The 5 existing tests in `backend/tests/test_agents/test_worker.py` construct `AgentWorker(...)` without a `dispatcher` arg. Each test should now build:

```python
from app.agents.dispatcher import Dispatcher

dispatcher = Dispatcher(cfg=FleetConfig().dispatch, bus=stack["bus"])
worker = AgentWorker(
    registry=reg,
    nodes=stack["nodes"],
    edges=stack["edges"],
    bus=stack["bus"],
    llm_cfg=LLMConfig(provider="anthropic", model="x", api_key_env="X"),
    fleet=FleetConfig(agents=[spec]),
    vault_path=stack["vault"],
    repo_path=stack["repo"],
    dispatcher=dispatcher,
)
```

Apply this to all 5 tests in `backend/tests/test_agents/test_worker.py`. (Default `DispatchConfig(max_parallel=1)` preserves serial behavior, so the tests' existing assertions stand.)

- [ ] **Step 6: Run the full agents test suite to verify it passes**

Run: `cd backend && uv run pytest tests/test_agents -v`
Expected: All tests PASS — original 5 worker tests + 3 new parallel tests + 8 dispatcher tests + existing config/registry/api/runtime tests.

- [ ] **Step 7: Commit**

```bash
git add backend/app/agents/worker.py backend/app/main.py backend/tests/test_agents/test_worker.py backend/tests/test_agents/test_worker_parallel.py
git commit -m "feat(agents): route AgentWorker firings through Dispatcher (Plan 07 task 4)"
```

---

## Task 5: `GET /agents/inflight` endpoint

**Files:**
- Modify: `backend/app/agents/api.py`
- Modify: `backend/app/main.py` — pass `dispatcher` to `build_agents_router`
- Test: `backend/tests/test_agents/test_api.py`

Exposes the dispatcher's `in_flight()` snapshot so the brain view can display "running agents now" without subscribing to SSE.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_agents/test_api.py`:

```python
def test_inflight_returns_empty_when_idle(client_with_dispatcher):
    client, _ = client_with_dispatcher
    r = client.get("/agents/inflight")
    assert r.status_code == 200
    assert r.json() == []


def test_inflight_returns_running_firings(client_with_dispatcher):
    client, dispatcher = client_with_dispatcher
    # Inject a fake in-flight entry (test-only — production fills it via dispatch)
    dispatcher._inflight["fid-X"] = {
        "firing_id": "fid-X",
        "role": "cto",
        "started_at": 1234567890.0,
    }
    try:
        r = client.get("/agents/inflight")
        assert r.status_code == 200
        body = r.json()
        assert body == [
            {"firing_id": "fid-X", "role": "cto", "started_at": 1234567890.0}
        ]
    finally:
        dispatcher._inflight.pop("fid-X", None)
```

And add the `client_with_dispatcher` fixture at the top of `test_api.py` (or in `conftest.py` if it already has TestClient setup):

```python
@pytest.fixture
def client_with_dispatcher(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.agents.api import build_agents_router
    from app.agents.config import DispatchConfig
    from app.agents.dispatcher import Dispatcher
    from app.agents.registry import AgentRegistry
    from app.db.kuzu import KuzuConnection
    from app.db.nodes import NodeRepository

    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    registry = AgentRegistry(nodes=nodes, conn=conn)
    dispatcher = Dispatcher(cfg=DispatchConfig(max_parallel=2))
    app = FastAPI()
    app.include_router(
        build_agents_router(registry=registry, conn=conn, dispatcher=dispatcher)
    )
    yield TestClient(app), dispatcher
    conn.close()
```

(Add `import pytest` and `from pathlib import Path` if missing.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_agents/test_api.py -v`
Expected: FAIL — `build_agents_router` rejects the `dispatcher` kwarg.

- [ ] **Step 3: Extend `build_agents_router` with `/agents/inflight`**

Modify `backend/app/agents/api.py`:

```python
from fastapi import APIRouter, HTTPException

from app.agents.dispatcher import Dispatcher
from app.agents.registry import AgentRegistry
from app.db.kuzu import KuzuConnection


def build_agents_router(
    *,
    registry: AgentRegistry,
    conn: KuzuConnection,
    dispatcher: Dispatcher,
) -> APIRouter:
    router = APIRouter()

    @router.get("/agents")
    def list_agents() -> list[dict]:
        return registry.list_agents()

    @router.get("/agents/inflight")
    def inflight() -> list[dict]:
        return dispatcher.in_flight()

    @router.post("/agents/{agent_id}/pause")
    def pause(agent_id: str) -> dict:
        if registry.get_by_id(agent_id) is None:
            raise HTTPException(status_code=404, detail=f"agent {agent_id} not found")
        conn.query(
            "MATCH (a:Agent) WHERE a.id = $id SET a.state = 'paused'",
            {"id": agent_id},
        )
        return {"id": agent_id, "state": "paused"}

    @router.post("/agents/{agent_id}/resume")
    def resume(agent_id: str) -> dict:
        if registry.get_by_id(agent_id) is None:
            raise HTTPException(status_code=404, detail=f"agent {agent_id} not found")
        conn.query(
            "MATCH (a:Agent) WHERE a.id = $id SET a.state = 'idle'",
            {"id": agent_id},
        )
        return {"id": agent_id, "state": "idle"}

    return router
```

- [ ] **Step 4: Wire dispatcher into `main.py` router include**

In `backend/app/main.py`, find the line that builds the agents router and pass `dispatcher`:

```python
app.include_router(
    build_agents_router(registry=registry, conn=conn, dispatcher=dispatcher)
)
```

(If `build_agents_router` is not yet included in `main.py`'s lifespan — check via `grep -n build_agents_router backend/app/main.py` — add the include alongside the other router includes.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_agents/test_api.py -v`
Expected: PASS, including the 2 new tests.

Then run the full backend suite to ensure nothing else broke:

Run: `cd backend && uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents/api.py backend/app/main.py backend/tests/test_agents/test_api.py
git commit -m "feat(api): GET /agents/inflight exposes dispatcher state (Plan 07 task 5)"
```

---

## Task 6: Update `agents.yaml.example` and `docs/self-hosting.md`

**Files:**
- Modify: `backend/agents.yaml.example`
- Modify: `docs/self-hosting.md`

Docs-only task — no code, no tests. Tells operators how to opt into parallel dispatch.

- [ ] **Step 1: Append the `dispatch:` block to `agents.yaml.example`**

Append to `backend/agents.yaml.example`:

```yaml

# Optional: bounded-concurrency dispatch (defaults to fully sequential).
#
# `max_parallel` caps the total number of concurrent agent runs across all roles.
# `per_role` tightens individual roles below the global cap — useful when a role's
# workspace can't tolerate concurrent writers (e.g. two CTO agents racing on the
# same architecture doc).
#
# dispatch:
#   max_parallel: 3
#   per_role:
#     cto: 1
#     engineer: 2
```

- [ ] **Step 2: Append the parallel-dispatch section to `docs/self-hosting.md`**

Open `docs/self-hosting.md` and add a new section after the existing config/environment sections. Use this exact content:

```markdown
## Parallel agent dispatch

By default, the v2 agent worker runs one agent at a time. To process multiple
`fire.neuron` events concurrently, set a `dispatch:` block in your `agents.yaml`:

```yaml
dispatch:
  max_parallel: 3        # up to 3 agent runs at once across the whole fleet
  per_role:
    cto: 1               # never run two CTO agents concurrently
    engineer: 2          # up to 2 engineer agents concurrently
```

Semantics:

- **Per-role serialization:** two firings for the same role never overlap, even
  when the global cap allows it. This avoids two agents in the same role racing
  on a shared workspace.
- **Failure isolation:** an agent run raising an exception marks that firing as
  `outcome=failed` in the graph and does not abort sibling runs.
- **Progress events:** every run emits `agent.run.started` and
  `agent.run.completed` events over the SSE `/stream` channel, tagged with
  `firing_id` so the brain view can correlate.
- **Live state:** `GET /agents/inflight` returns the dispatcher's current
  snapshot: `[{firing_id, role, started_at}]`.
```

(Note: the inner triple-backtick yaml block must remain — make sure your editor preserves it.)

- [ ] **Step 3: Commit**

```bash
git add backend/agents.yaml.example docs/self-hosting.md
git commit -m "docs: document parallel agent dispatch (Plan 07 task 6)"
```

---

## Task 7: End-to-end concurrency smoke

**Files:**
- Test: `backend/tests/test_agents/test_e2e_fire_neuron.py` (modify the existing file)

Validates the full pipeline: `bus.publish(FireNeuron)` → worker → dispatcher → fake runtime → events emitted → graph state correct. The existing e2e test runs one firing; this adds a multi-firing case.

- [ ] **Step 1: Inspect the existing e2e test**

Read `backend/tests/test_agents/test_e2e_fire_neuron.py` to understand its fixture and stubbing pattern. The new test reuses the same fixture style.

Run: `cd backend && uv run pytest tests/test_agents/test_e2e_fire_neuron.py -v`
Expected: existing test(s) PASS (after Task 4 already updated them to take a dispatcher).

- [ ] **Step 2: Append the multi-firing e2e test**

The existing `test_e2e_fire_neuron.py` inlines its setup in `tmp_path` rather than using a fixture. Match that pattern. Append to `backend/tests/test_agents/test_e2e_fire_neuron.py`:

```python
@pytest.mark.asyncio
async def test_e2e_three_concurrent_firings_emit_three_completion_events(
    tmp_path: Path, monkeypatch
):
    """Three distinct-role firings under max_parallel=3 produce three success
    outcomes in the graph and three agent.run.completed events on the bus."""
    from app.agents.config import DispatchConfig
    from app.agents.dispatcher import Dispatcher
    from app.events.schemas import AgentRunCompleted

    conn = KuzuConnection(str(tmp_path / "e2e_parallel.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    edges = EdgeRepository(conn)
    bus = EventBus()

    specs = [
        AgentSpec(id="cto-1", role="cto", persona="x"),
        AgentSpec(id="eng-1", role="engineer", persona="x"),
        AgentSpec(id="pm-1", role="pm", persona="x"),
    ]
    fleet = FleetConfig(agents=specs, dispatch=DispatchConfig(max_parallel=3))
    AgentRegistry(nodes=nodes, conn=conn).sync(fleet)

    def fake_init(self, *, spec, llm_cfg, vault_path, repo_path):
        self.spec = spec

    async def fake_run(self, *, firing_id, task_summary):
        await asyncio.sleep(0.02)
        return AgentRunResult(summary="ok")

    monkeypatch.setattr("app.agents.runtime.AgentRuntime.__init__", fake_init)
    monkeypatch.setattr("app.agents.runtime.AgentRuntime.run", fake_run)

    dispatcher = Dispatcher(cfg=fleet.dispatch, bus=bus)
    completed_events: list = []

    async def on_completed(e: AgentRunCompleted):
        completed_events.append(e)

    bus.subscribe("agent.run.completed", on_completed)

    worker = AgentWorker(
        registry=AgentRegistry(nodes=nodes, conn=conn),
        nodes=nodes,
        edges=edges,
        bus=bus,
        llm_cfg=LLMConfig(provider="anthropic", model="x", api_key_env="X"),
        fleet=fleet,
        vault_path=str(tmp_path / "vault"),
        repo_path=None,
        dispatcher=dispatcher,
    )
    worker.attach()

    thoughts = []
    for i, role in enumerate(["cto", "engineer", "pm"]):
        t = ThoughtNode(content=f"t{i}", source="cli")
        nodes.create(t)
        thoughts.append((t, role))

    await asyncio.gather(
        *(
            bus.publish(
                FireNeuron(thought_id=t.id, agent_role=role, task_summary="x")
            )
            for t, role in thoughts
        )
    )
    await asyncio.sleep(0.3)

    firings = conn.query(
        "MATCH (f:AgentFiring) RETURN f.agent_id AS agent_id, f.outcome AS outcome"
    )
    assert len(firings) == 3
    assert {f["agent_id"] for f in firings} == {"cto-1", "eng-1", "pm-1"}
    assert all(f["outcome"] == "success" for f in firings)
    assert len(completed_events) == 3
    assert {e.role for e in completed_events} == {"cto", "engineer", "pm"}
    assert all(e.outcome == "success" for e in completed_events)
    conn.close()
```

The top-of-file imports (`asyncio`, `pytest`, `Path`, `AgentSpec`, `FleetConfig`, `AgentRegistry`, `AgentRunResult`, `AgentWorker`, `LLMConfig`, `EdgeRepository`, `KuzuConnection`, `NodeRepository`, `ThoughtNode`, `EventBus`, `FireNeuron`) are already present from the existing test. The new test adds local imports for `DispatchConfig`, `Dispatcher`, and `AgentRunCompleted`.

- [ ] **Step 3: Run the new test**

Run: `cd backend && uv run pytest tests/test_agents/test_e2e_fire_neuron.py -v`
Expected: PASS, including the new test.

- [ ] **Step 4: Run full backend suite**

Run: `cd backend && uv run pytest -v 2>&1 | tail -30`
Expected: All tests PASS. Note the total count is the baseline (91 from PR #65) + ~17 new tests added across this plan (≈108 total).

- [ ] **Step 5: Run lint**

Run: `cd backend && uv run ruff check . && uv run ruff format --check .`
Expected: Clean. If `ruff format` reports diffs, run `uv run ruff format .` and stage the result.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_agents/test_e2e_fire_neuron.py
git commit -m "test(agents): e2e — three concurrent firings emit three completion events (Plan 07 task 7)"
```

---

## Done — Plan 07 deliverable

After this PR merges:

- `agents.yaml`'s new `dispatch:` block opts a self-hosted instance into bounded parallel agent dispatch.
- Per-role serialization prevents same-role races.
- Per-firing failures are isolated; siblings complete.
- The brain view's SSE stream gains `agent.run.started` and `agent.run.completed` events tagged with `firing_id`.
- `GET /agents/inflight` exposes the live in-flight snapshot.
- Default behavior (no `dispatch:` block) is unchanged from v0.1: `max_parallel=1`.

## Test plan (PR description)

- [ ] CI: `backend-ci` green
- [ ] `cd backend && uv run pytest` → all pass (≈108 tests)
- [ ] `cd backend && uv run ruff check . && uv run ruff format --check .` → clean
- [ ] Manual: start `docker compose up`, POST 3 `/capture` events targeting different roles, observe 3 concurrent firings via `GET /agents/inflight` and via SSE `/stream` (3 `agent.run.started` events overlap in time)
- [ ] Manual: set `dispatch.max_parallel: 1` and POST 3 events — observe sequential firings via SSE timestamps
