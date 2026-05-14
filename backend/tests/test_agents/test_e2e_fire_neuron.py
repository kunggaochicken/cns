import asyncio
from pathlib import Path

import pytest

from app.agents.config import AgentSpec, FleetConfig
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


@pytest.mark.asyncio
async def test_fire_neuron_creates_firing_and_edges(tmp_path: Path, monkeypatch):
    conn = KuzuConnection(str(tmp_path / "e2e.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    edges = EdgeRepository(conn)
    bus = EventBus()

    thought = ThoughtNode(content="add /capture endpoint", source="cli")
    nodes.create(thought)

    spec = AgentSpec(id="eng-1", role="engineer", persona="x")
    fleet = FleetConfig(agents=[spec])
    AgentRegistry(nodes=nodes, conn=conn).sync(fleet)

    fake_result = AgentRunResult(summary="drafted endpoint")

    async def fake_run(self, *, firing_id, task_summary):
        return fake_result

    monkeypatch.setattr(
        "app.agents.runtime.AgentRuntime.__init__",
        lambda self, *, spec, llm_cfg, vault_path, repo_path: setattr(
            self, "spec", spec
        ),
    )
    monkeypatch.setattr("app.agents.runtime.AgentRuntime.run", fake_run)

    dispatcher = Dispatcher(cfg=FleetConfig().dispatch, bus=bus)
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

    await bus.publish(
        FireNeuron(
            thought_id=thought.id,
            agent_role="engineer",
            task_summary="add /capture",
        )
    )
    await asyncio.sleep(0.2)

    firings = conn.query(
        "MATCH (f:AgentFiring) RETURN f.id AS id, f.outcome AS outcome, "
        "f.agent_id AS agent_id"
    )
    assert len(firings) == 1
    assert firings[0]["outcome"] == "success"

    firing_id = firings[0]["id"]
    produced = conn.query(
        "MATCH (a:Agent)-[r:REL]->(f:AgentFiring) "
        "WHERE r.edge_type = 'produced' AND f.id = $fid RETURN a.id AS aid",
        {"fid": firing_id},
    )
    assert len(produced) == 1
    assert produced[0]["aid"] == "eng-1"

    fired_from = conn.query(
        "MATCH (f:AgentFiring)-[r:REL]->(t:Thought) "
        "WHERE r.edge_type = 'fired-from' AND f.id = $fid RETURN t.id AS tid",
        {"fid": firing_id},
    )
    assert len(fired_from) == 1
    assert fired_from[0]["tid"] == thought.id

    conn.close()


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
            bus.publish(FireNeuron(thought_id=t.id, agent_role=role, task_summary="x"))
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
