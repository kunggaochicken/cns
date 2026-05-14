import asyncio

import pytest

from app.agents.config import DispatchConfig
from app.agents.dispatcher import Dispatcher
from app.events.bus import EventBus
from app.events.schemas import AgentRunCompleted, AgentRunStarted


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
    assert any(s == ("completed", "fid-A", "engineer", "success") for s in seen)


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
