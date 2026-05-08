import asyncio
from pathlib import Path

import pytest

from app.agents.config import AgentSpec, FleetConfig
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

    worker = AgentWorker(
        registry=AgentRegistry(nodes=nodes, conn=conn),
        nodes=nodes,
        edges=edges,
        bus=bus,
        llm_cfg=LLMConfig(provider="anthropic", model="x", api_key_env="X"),
        fleet=fleet,
        vault_path=str(tmp_path / "vault"),
        repo_path=None,
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
