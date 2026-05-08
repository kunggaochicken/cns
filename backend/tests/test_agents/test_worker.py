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
async def test_worker_processes_fire_neuron_for_matching_role(stack, monkeypatch):
    reg = AgentRegistry(nodes=stack["nodes"], conn=stack["conn"])
    spec = AgentSpec(id="eng-1", role="engineer", persona="x")
    reg.sync(FleetConfig(agents=[spec]))

    # Stub AgentRuntime: avoid real LLM init + return canned output
    fake_result = AgentRunResult(summary="drafted /capture endpoint")

    def fake_init(self, *, spec, llm_cfg, vault_path, repo_path):
        self.spec = spec
        self.vault_path = vault_path
        self.repo_path = repo_path

    async def fake_run(self, *, firing_id, task_summary):
        return fake_result

    monkeypatch.setattr("app.agents.runtime.AgentRuntime.__init__", fake_init)
    monkeypatch.setattr("app.agents.runtime.AgentRuntime.run", fake_run)

    worker = AgentWorker(
        registry=reg,
        nodes=stack["nodes"],
        edges=stack["edges"],
        bus=stack["bus"],
        llm_cfg=LLMConfig(provider="anthropic", model="x", api_key_env="X"),
        fleet=FleetConfig(agents=[spec]),
        vault_path=stack["vault"],
        repo_path=stack["repo"],
    )
    worker.attach()

    # Pre-create a thought so the fired-from edge has a valid target
    from app.db.schemas import ThoughtNode

    thought = ThoughtNode(content="add /capture", source="cli")
    stack["nodes"].create(thought)

    await stack["bus"].publish(
        FireNeuron(
            thought_id=thought.id,
            agent_role="engineer",
            task_summary="add /capture",
        )
    )
    await asyncio.sleep(0.2)

    firings = stack["conn"].query(
        "MATCH (f:AgentFiring) RETURN f.id AS id, f.outcome AS outcome, "
        "f.agent_id AS agent_id"
    )
    assert len(firings) == 1
    assert firings[0]["agent_id"] == "eng-1"
    assert firings[0]["outcome"] == "success"


@pytest.mark.asyncio
async def test_worker_drops_event_when_no_agent_matches_role(stack, caplog):
    reg = AgentRegistry(nodes=stack["nodes"], conn=stack["conn"])
    reg.sync(
        FleetConfig(
            agents=[
                AgentSpec(id="eng-1", role="engineer", persona="x"),
            ]
        )
    )
    worker = AgentWorker(
        registry=reg,
        nodes=stack["nodes"],
        edges=stack["edges"],
        bus=stack["bus"],
        llm_cfg=LLMConfig(provider="anthropic", model="x", api_key_env="X"),
        fleet=FleetConfig(agents=[AgentSpec(id="eng-1", role="engineer", persona="x")]),
        vault_path=stack["vault"],
        repo_path=stack["repo"],
    )
    worker.attach()
    await stack["bus"].publish(
        FireNeuron(
            thought_id="t_missing",
            agent_role="cto",
            task_summary="x",
        )
    )
    await asyncio.sleep(0.1)

    # No firing should be created
    firings = stack["conn"].query("MATCH (f:AgentFiring) RETURN f.id AS id")
    assert len(firings) == 0
