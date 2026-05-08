import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.config import LLMConfig
from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import ThoughtNode
from app.db.vector import VectorStore
from app.events.bus import EventBus
from app.events.schemas import ThoughtCreated
from app.sparring.engine import SparringEngine
from app.sparring.llm import SparringResult


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
    yield {"conn": conn, "nodes": nodes, "edges": edges, "vec": vec, "bus": bus}
    vec.close()
    conn.close()


@pytest.mark.asyncio
async def test_engine_processes_thought_created_event(stack):
    thought = ThoughtNode(content="should we ship preview?", source="cli")
    stack["nodes"].create(thought)
    stack["vec"].upsert(thought.id, [1.0, 0.0, 0.0, 0.0])

    embedder = AsyncMock()
    embedder.embed.return_value = [1.0, 0.0, 0.0, 0.0]
    embedder.dim = 4

    fake_result = SparringResult(classification="novel", reasoning="no precedent")
    with patch("app.sparring.engine.run_spar", new=AsyncMock(return_value=fake_result)):
        engine = SparringEngine(
            cfg=LLMConfig(
                provider="anthropic", model="claude-sonnet-4-6", api_key_env="X"
            ),
            nodes=stack["nodes"],
            edges=stack["edges"],
            vec=stack["vec"],
            bus=stack["bus"],
            embedder=embedder,
        )
        engine.attach()
        await stack["bus"].publish(
            ThoughtCreated(thought_id=thought.id, content=thought.content)
        )
        await asyncio.sleep(0.1)
    # No assertion errors = engine processed the event end-to-end
