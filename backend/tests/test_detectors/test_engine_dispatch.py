import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.config import DetectorsConfig, LLMConfig
from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import ThoughtNode
from app.db.vector import VectorStore
from app.detectors.base import DetectorOutcome
from app.events.bus import EventBus
from app.events.schemas import ThoughtCreated
from app.sparring.engine import SparringEngine


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
        "vault": str(vault),
        "tmp": tmp_path,
    }
    vec.close()
    conn.close()


@pytest.mark.asyncio
async def test_engine_dispatches_to_all_enabled_detectors(stack):
    thought = ThoughtNode(content="should we ship preview?", source="cli")
    stack["nodes"].create(thought)
    stack["vec"].upsert(thought.id, [1.0, 0.0, 0.0, 0.0])

    embedder = AsyncMock()
    embedder.embed.return_value = [1.0, 0.0, 0.0, 0.0]
    embedder.dim = 4

    engine = SparringEngine(
        cfg=LLMConfig(provider="anthropic", model="claude-sonnet-4-6", api_key_env="X"),
        detectors_cfg=DetectorsConfig(),
        conn=stack["conn"],
        nodes=stack["nodes"],
        edges=stack["edges"],
        vec=stack["vec"],
        bus=stack["bus"],
        embedder=embedder,
        vault_path=stack["vault"],
    )

    # Replace each detector's run with a recorder
    calls = []
    for det in engine.detectors:
        det.run = AsyncMock(
            return_value=DetectorOutcome(
                detector=det.name,
                thought_id=thought.id,
            )
        )
        calls.append(det)

    engine.attach()
    await stack["bus"].publish(
        ThoughtCreated(thought_id=thought.id, content=thought.content)
    )
    await asyncio.sleep(0.05)

    names = {d.name for d in calls}
    assert names == {"duplicate", "conflict"}
    for det in calls:
        det.run.assert_called_once()


@pytest.mark.asyncio
async def test_engine_disabled_detector_not_registered(stack):
    embedder = AsyncMock()
    engine = SparringEngine(
        cfg=LLMConfig(provider="anthropic", model="claude-sonnet-4-6", api_key_env="X"),
        detectors_cfg=DetectorsConfig(duplicate_enabled=False, conflict_enabled=True),
        conn=stack["conn"],
        nodes=stack["nodes"],
        edges=stack["edges"],
        vec=stack["vec"],
        bus=stack["bus"],
        embedder=embedder,
        vault_path=stack["vault"],
    )
    names = {d.name for d in engine.detectors}
    assert names == {"conflict"}


@pytest.mark.asyncio
async def test_one_detector_failing_does_not_block_others(stack):
    thought = ThoughtNode(content="x", source="cli")
    stack["nodes"].create(thought)
    stack["vec"].upsert(thought.id, [1.0, 0.0, 0.0, 0.0])
    embedder = AsyncMock()
    embedder.embed.return_value = [1.0, 0.0, 0.0, 0.0]

    engine = SparringEngine(
        cfg=LLMConfig(provider="anthropic", model="claude-sonnet-4-6", api_key_env="X"),
        detectors_cfg=DetectorsConfig(),
        conn=stack["conn"],
        nodes=stack["nodes"],
        edges=stack["edges"],
        vec=stack["vec"],
        bus=stack["bus"],
        embedder=embedder,
        vault_path=stack["vault"],
    )
    engine.detectors[0].run = AsyncMock(side_effect=RuntimeError("boom"))
    engine.detectors[1].run = AsyncMock(
        return_value=DetectorOutcome(
            detector=engine.detectors[1].name,
            thought_id=thought.id,
        )
    )
    engine.attach()
    await stack["bus"].publish(
        ThoughtCreated(thought_id=thought.id, content=thought.content)
    )
    await asyncio.sleep(0.05)
    engine.detectors[1].run.assert_called_once()
