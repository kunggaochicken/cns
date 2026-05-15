import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import LLMConfig
from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import ThoughtNode
from app.db.vector import VectorStore
from app.detectors.conflict import ConflictConfig, ConflictDetector
from app.detectors.llm_clients import ConflictVerdict
from app.events.bus import EventBus


@pytest.fixture
def stack(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    edges = EdgeRepository(conn)
    vec = VectorStore(str(tmp_path / "v.sqlite"), dim=4)
    vec.connect()
    bus = EventBus()
    vault = tmp_path / "vault"
    vault.mkdir()
    yield {
        "conn": conn,
        "nodes": nodes,
        "edges": edges,
        "vec": vec,
        "bus": bus,
        "vault": vault,
    }
    vec.close()
    conn.close()


def _mk_agent(verdict: ConflictVerdict) -> MagicMock:
    agent = MagicMock()
    agent.run = AsyncMock(return_value=MagicMock(output=verdict))
    return agent


@pytest.mark.asyncio
async def test_writes_contradicts_edge_and_conflict_node_on_match(stack):
    old = ThoughtNode(content="we agreed to delay preview a month", source="cli")
    stack["nodes"].create(old)
    stack["vec"].upsert(old.id, [1.0, 0.0, 0.0, 0.0])
    new = ThoughtNode(content="we should ship preview now", source="cli")
    stack["nodes"].create(new)
    stack["vec"].upsert(new.id, [1.0, 0.0, 0.0, 0.0])

    agent = _mk_agent(
        ConflictVerdict(
            contradicts=True,
            summary="ship-now vs delay-a-month",
            reasoning="contradictory timing",
            confidence=0.85,
        )
    )
    det = ConflictDetector(
        llm_cfg=LLMConfig(
            provider="anthropic", model="claude-sonnet-4-6", api_key_env="X"
        ),
        conn=stack["conn"],
        nodes=stack["nodes"],
        edges=stack["edges"],
        vec=stack["vec"],
        bus=stack["bus"],
        vault_path=stack["vault"],
        agent=agent,
    )
    outcome = await det.run(
        thought_id=new.id, content=new.content, embedding=[1.0, 0.0, 0.0, 0.0]
    )
    assert outcome.nodes_written == 1
    out = stack["edges"].list_outgoing(new.id, "Thought")
    assert any(e["edge_type"] == "contradicts" and e["to_id"] == old.id for e in out)
    assert any(e["edge_type"] == "led-to" for e in out)
    # Sidecar markdown landed in the vault
    sidecars = list((stack["vault"] / "Brain" / "Reviews" / "conflicts").glob("*.md"))
    assert len(sidecars) == 1


@pytest.mark.asyncio
async def test_no_write_when_llm_says_no_contradiction(stack):
    old = ThoughtNode(content="alpha", source="cli")
    stack["nodes"].create(old)
    stack["vec"].upsert(old.id, [1.0, 0.0, 0.0, 0.0])
    new = ThoughtNode(content="beta", source="cli")
    stack["nodes"].create(new)
    stack["vec"].upsert(new.id, [1.0, 0.0, 0.0, 0.0])

    agent = _mk_agent(
        ConflictVerdict(
            contradicts=False, summary="", reasoning="aligned", confidence=0.9
        )
    )
    det = ConflictDetector(
        llm_cfg=LLMConfig(
            provider="anthropic", model="claude-sonnet-4-6", api_key_env="X"
        ),
        conn=stack["conn"],
        nodes=stack["nodes"],
        edges=stack["edges"],
        vec=stack["vec"],
        bus=stack["bus"],
        vault_path=stack["vault"],
        agent=agent,
    )
    outcome = await det.run(
        thought_id=new.id, content=new.content, embedding=[1.0, 0.0, 0.0, 0.0]
    )
    assert outcome.edges_written == 0
    assert outcome.nodes_written == 0


@pytest.mark.asyncio
async def test_drops_low_confidence(stack):
    old = ThoughtNode(content="alpha", source="cli")
    stack["nodes"].create(old)
    stack["vec"].upsert(old.id, [1.0, 0.0, 0.0, 0.0])
    new = ThoughtNode(content="beta", source="cli")
    stack["nodes"].create(new)
    stack["vec"].upsert(new.id, [1.0, 0.0, 0.0, 0.0])

    agent = _mk_agent(
        ConflictVerdict(
            contradicts=True, summary="maybe", reasoning="unsure", confidence=0.3
        )
    )
    det = ConflictDetector(
        llm_cfg=LLMConfig(
            provider="anthropic", model="claude-sonnet-4-6", api_key_env="X"
        ),
        conn=stack["conn"],
        nodes=stack["nodes"],
        edges=stack["edges"],
        vec=stack["vec"],
        bus=stack["bus"],
        vault_path=stack["vault"],
        agent=agent,
        cfg=ConflictConfig(min_confidence=0.6),
    )
    outcome = await det.run(
        thought_id=new.id, content=new.content, embedding=[1.0, 0.0, 0.0, 0.0]
    )
    assert outcome.edges_written == 0


@pytest.mark.asyncio
async def test_publishes_graph_changed_on_match(stack):
    old = ThoughtNode(content="x", source="cli")
    stack["nodes"].create(old)
    stack["vec"].upsert(old.id, [1.0, 0.0, 0.0, 0.0])
    new = ThoughtNode(content="y", source="cli")
    stack["nodes"].create(new)
    stack["vec"].upsert(new.id, [1.0, 0.0, 0.0, 0.0])

    received = []

    async def handler(ev):
        received.append(ev)

    stack["bus"].subscribe("graph.changed", handler)

    agent = _mk_agent(
        ConflictVerdict(contradicts=True, summary="s", reasoning="r", confidence=0.9)
    )
    det = ConflictDetector(
        llm_cfg=LLMConfig(
            provider="anthropic", model="claude-sonnet-4-6", api_key_env="X"
        ),
        conn=stack["conn"],
        nodes=stack["nodes"],
        edges=stack["edges"],
        vec=stack["vec"],
        bus=stack["bus"],
        vault_path=stack["vault"],
        agent=agent,
    )
    await det.run(
        thought_id=new.id, content=new.content, embedding=[1.0, 0.0, 0.0, 0.0]
    )
    await asyncio.sleep(0.05)
    assert any(e.change_type == "node_created" for e in received)
