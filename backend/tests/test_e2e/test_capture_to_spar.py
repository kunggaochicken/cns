# backend/tests/test_e2e/test_capture_to_spar.py
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.capture.normalizer import normalize_and_persist
from app.config import LLMConfig
from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import BetNode
from app.db.vector import VectorStore
from app.events.bus import EventBus
from app.sparring.engine import SparringEngine
from app.sparring.llm import SparringEdge, SparringResult


@pytest.mark.asyncio
async def test_thought_captured_and_sparred_creates_edge_to_existing_bet(
    tmp_path: Path,
):
    conn = KuzuConnection(str(tmp_path / "e2e.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    edges = EdgeRepository(conn)
    vec = VectorStore(str(tmp_path / "e2e-vec.sqlite"), dim=4)
    vec.connect()
    bus = EventBus()

    bet = BetNode(
        slug="auth_pivot", title="Pivot to OAuth", vault_path="x.md", owner="cto"
    )
    nodes.create(bet)
    vec.upsert(bet.id, [1.0, 0.0, 0.0, 0.0])

    embedder = AsyncMock()
    embedder.embed.return_value = [0.95, 0.05, 0.0, 0.0]
    embedder.dim = 4

    fake_spar = SparringResult(
        classification="conflict",
        reasoning="Contradicts auth_pivot bet",
        edges_to_record=[
            SparringEdge(target_id=bet.id, edge_type="contradicts", confidence=0.9),
        ],
    )
    with patch("app.sparring.engine.run_spar", new=AsyncMock(return_value=fake_spar)):
        engine = SparringEngine(
            cfg=LLMConfig(provider="anthropic", model="x", api_key_env="X"),
            nodes=nodes,
            edges=edges,
            vec=vec,
            bus=bus,
            embedder=embedder,
        )
        engine.attach()

        thought = await normalize_and_persist(
            content="we should drop oauth",
            source="cli",
            metadata={},
            nodes=nodes,
            vec=vec,
            bus=bus,
            embedder=embedder,
        )

        # Allow async sparring + routing to complete
        await asyncio.sleep(0.3)

    # 1. Thought node exists
    fetched = nodes.get(thought.id, "Thought")
    assert fetched is not None

    # 2. contradicts edge from thought to bet was created
    outgoing = edges.list_outgoing(thought.id, "Thought")
    contradicts_edges = [e for e in outgoing if e["edge_type"] == "contradicts"]
    assert len(contradicts_edges) == 1
    assert contradicts_edges[0]["to_id"] == bet.id

    # 3. A GateItem was created (because classification was conflict)
    all_gates = conn.query("MATCH (g:GateItem) RETURN g.id AS id")
    assert len(all_gates) == 1

    vec.close()
    conn.close()
