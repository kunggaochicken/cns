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
from app.events.schemas import FireNeuron, GraphChanged


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
        stack["bus"].publish(
            FireNeuron(thought_id=thoughts[0].id, agent_role="cto", task_summary="x")
        ),
        stack["bus"].publish(
            FireNeuron(
                thought_id=thoughts[1].id, agent_role="engineer", task_summary="x"
            )
        ),
        stack["bus"].publish(
            FireNeuron(thought_id=thoughts[2].id, agent_role="pm", task_summary="x")
        ),
    )
    await asyncio.sleep(0.2)

    assert max_seen == 3
    firings = stack["conn"].query("MATCH (f:AgentFiring) RETURN f.outcome AS outcome")
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
        stack["bus"].publish(
            FireNeuron(thought_id=t1.id, agent_role="cto", task_summary="x")
        ),
        stack["bus"].publish(
            FireNeuron(thought_id=t2.id, agent_role="cto", task_summary="x")
        ),
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
        stack["bus"].publish(
            FireNeuron(thought_id=t1.id, agent_role="cto", task_summary="x")
        ),
        stack["bus"].publish(
            FireNeuron(thought_id=t2.id, agent_role="engineer", task_summary="x")
        ),
    )
    await asyncio.sleep(0.2)

    firings = stack["conn"].query(
        "MATCH (f:AgentFiring) RETURN f.agent_id AS agent_id, f.outcome AS outcome"
    )
    by_agent = {f["agent_id"]: f["outcome"] for f in firings}
    assert by_agent == {"cto-1": "failed", "eng-1": "success"}


@pytest.mark.asyncio
async def test_worker_emits_graph_changed_when_firing_is_created(stack, monkeypatch):
    """A new AgentFiring must trigger a GraphChanged so the brain view updates."""
    reg = AgentRegistry(nodes=stack["nodes"], conn=stack["conn"])
    spec = AgentSpec(id="eng-1", role="engineer", persona="x")
    reg.sync(FleetConfig(agents=[spec]))

    def fake_init(self, *, spec, llm_cfg, vault_path, repo_path):
        self.spec = spec

    async def fake_run(self, *, firing_id, task_summary):
        return AgentRunResult(summary="ok")

    monkeypatch.setattr("app.agents.runtime.AgentRuntime.__init__", fake_init)
    monkeypatch.setattr("app.agents.runtime.AgentRuntime.run", fake_run)

    graph_events: list[GraphChanged] = []

    async def on_graph(e: GraphChanged):
        graph_events.append(e)

    stack["bus"].subscribe("graph.changed", on_graph)

    fleet = FleetConfig(agents=[spec])
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

    thought = ThoughtNode(content="x", source="cli")
    stack["nodes"].create(thought)

    await stack["bus"].publish(
        FireNeuron(
            thought_id=thought.id,
            agent_role="engineer",
            task_summary="x",
        )
    )
    await asyncio.sleep(0.2)

    firings = stack["conn"].query("MATCH (f:AgentFiring) RETURN f.id AS id")
    assert len(firings) == 1
    firing_id = firings[0]["id"]

    node_created = [
        e
        for e in graph_events
        if e.change_type == "node_created" and e.node_id == firing_id
    ]
    assert len(node_created) == 1
