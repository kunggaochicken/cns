from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import ThoughtNode
from app.db.vector import VectorStore
from app.detectors.duplicate import DuplicateConfig, DuplicateDetector
from app.detectors.llm_clients import DuplicateVerdict


@pytest.fixture
def stack(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    edges = EdgeRepository(conn)
    vec = VectorStore(str(tmp_path / "v.sqlite"), dim=4)
    vec.connect()
    yield {"conn": conn, "nodes": nodes, "edges": edges, "vec": vec}
    vec.close()
    conn.close()


def _mk_agent(verdict: DuplicateVerdict) -> MagicMock:
    agent = MagicMock()
    agent.run = AsyncMock(return_value=MagicMock(output=verdict))
    return agent


@pytest.mark.asyncio
async def test_writes_duplicate_of_edge_when_llm_says_same(stack):
    old = ThoughtNode(content="we should ship preview now", source="cli")
    stack["nodes"].create(old)
    stack["vec"].upsert(old.id, [1.0, 0.0, 0.0, 0.0])
    new = ThoughtNode(content="ship preview asap", source="cli")
    stack["nodes"].create(new)
    stack["vec"].upsert(new.id, [1.0, 0.0, 0.0, 0.0])  # cosine ~1

    agent = _mk_agent(
        DuplicateVerdict(relation="same", reasoning="restated", confidence=0.95)
    )
    det = DuplicateDetector(
        conn=stack["conn"], edges=stack["edges"], vec=stack["vec"], agent=agent
    )
    outcome = await det.run(
        thought_id=new.id, content=new.content, embedding=[1.0, 0.0, 0.0, 0.0]
    )
    assert outcome.edges_written == 1
    out = stack["edges"].list_outgoing(new.id, "Thought")
    assert any(e["edge_type"] == "duplicate-of" and e["to_id"] == old.id for e in out)


@pytest.mark.asyncio
async def test_writes_near_restatement_when_llm_says_near(stack):
    old = ThoughtNode(content="we want a preview launch this week", source="cli")
    stack["nodes"].create(old)
    stack["vec"].upsert(old.id, [1.0, 0.0, 0.0, 0.0])
    new = ThoughtNode(content="let's plan a preview push soon", source="cli")
    stack["nodes"].create(new)
    stack["vec"].upsert(new.id, [1.0, 0.0, 0.0, 0.0])

    agent = _mk_agent(
        DuplicateVerdict(relation="near", reasoning="overlap", confidence=0.7)
    )
    det = DuplicateDetector(
        conn=stack["conn"], edges=stack["edges"], vec=stack["vec"], agent=agent
    )
    await det.run(
        thought_id=new.id, content=new.content, embedding=[1.0, 0.0, 0.0, 0.0]
    )
    out = stack["edges"].list_outgoing(new.id, "Thought")
    assert any(e["edge_type"] == "near-restatement-of" for e in out)


@pytest.mark.asyncio
async def test_skips_when_below_threshold(stack):
    old = ThoughtNode(content="unrelated thought", source="cli")
    stack["nodes"].create(old)
    stack["vec"].upsert(old.id, [0.0, 1.0, 0.0, 0.0])  # orthogonal
    new = ThoughtNode(content="totally different topic", source="cli")
    stack["nodes"].create(new)
    stack["vec"].upsert(new.id, [1.0, 0.0, 0.0, 0.0])

    agent = _mk_agent(DuplicateVerdict(relation="same", reasoning="x", confidence=1.0))
    det = DuplicateDetector(
        conn=stack["conn"],
        edges=stack["edges"],
        vec=stack["vec"],
        agent=agent,
        cfg=DuplicateConfig(distance_threshold=0.05),  # very strict
    )
    outcome = await det.run(
        thought_id=new.id, content=new.content, embedding=[1.0, 0.0, 0.0, 0.0]
    )
    assert outcome.candidates_examined == 0
    assert outcome.edges_written == 0
    agent.run.assert_not_called()


@pytest.mark.asyncio
async def test_no_edge_when_llm_says_different(stack):
    old = ThoughtNode(content="alpha", source="cli")
    stack["nodes"].create(old)
    stack["vec"].upsert(old.id, [1.0, 0.0, 0.0, 0.0])
    new = ThoughtNode(content="beta", source="cli")
    stack["nodes"].create(new)
    stack["vec"].upsert(new.id, [1.0, 0.0, 0.0, 0.0])

    agent = _mk_agent(
        DuplicateVerdict(relation="different", reasoning="x", confidence=0.9)
    )
    det = DuplicateDetector(
        conn=stack["conn"], edges=stack["edges"], vec=stack["vec"], agent=agent
    )
    outcome = await det.run(
        thought_id=new.id, content=new.content, embedding=[1.0, 0.0, 0.0, 0.0]
    )
    assert outcome.edges_written == 0
