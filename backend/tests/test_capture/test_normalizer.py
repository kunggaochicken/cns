"""Tests for `normalize_and_persist`'s event-publication contract.

The capture pipeline must publish *both* `ThoughtCreated` (domain event the
sparring engine subscribes to) *and* `GraphChanged` (the SSE channel the
brain view consumes to update without a refresh).
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.capture.normalizer import normalize_and_persist
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.events.bus import EventBus
from app.events.schemas import GraphChanged, ThoughtCreated


@pytest.fixture
def stack(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "n.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    vec = VectorStore(str(tmp_path / "n-vec.sqlite"), dim=4)
    vec.connect()
    bus = EventBus()
    embedder = AsyncMock()
    embedder.embed.return_value = [0.1, 0.2, 0.3, 0.4]
    embedder.dim = 4
    yield {"nodes": nodes, "vec": vec, "bus": bus, "embedder": embedder}
    vec.close()
    conn.close()


@pytest.mark.asyncio
async def test_normalize_publishes_thought_created_and_graph_changed(stack):
    thought_events: list[ThoughtCreated] = []
    graph_events: list[GraphChanged] = []

    async def on_thought(e: ThoughtCreated):
        thought_events.append(e)

    async def on_graph(e: GraphChanged):
        graph_events.append(e)

    stack["bus"].subscribe("thought.created", on_thought)
    stack["bus"].subscribe("graph.changed", on_graph)

    thought = await normalize_and_persist(
        content="captured thought",
        source="cli",
        metadata={},
        nodes=stack["nodes"],
        vec=stack["vec"],
        bus=stack["bus"],
        embedder=stack["embedder"],
    )
    # Drain spawned handler tasks
    await asyncio.sleep(0.01)

    assert len(thought_events) == 1
    assert thought_events[0].thought_id == thought.id

    assert len(graph_events) == 1
    assert graph_events[0].change_type == "node_created"
    assert graph_events[0].node_id == thought.id


@pytest.mark.asyncio
async def test_normalize_dedups_identical_content(stack):
    """Re-capturing the same content+source returns the existing thought
    and does NOT emit ThoughtCreated/GraphChanged the second time. This
    prevents Obsidian re-saves from filling the graph with noisy duplicates.
    """
    thought_events: list[ThoughtCreated] = []
    graph_events: list[GraphChanged] = []

    async def on_thought(e: ThoughtCreated):
        thought_events.append(e)

    async def on_graph(e: GraphChanged):
        graph_events.append(e)

    stack["bus"].subscribe("thought.created", on_thought)
    stack["bus"].subscribe("graph.changed", on_graph)

    first = await normalize_and_persist(
        content="hello world",
        source="obsidian",
        metadata={"vault_path": "note.md"},
        nodes=stack["nodes"],
        vec=stack["vec"],
        bus=stack["bus"],
        embedder=stack["embedder"],
    )
    second = await normalize_and_persist(
        content="hello world",
        source="obsidian",
        metadata={"vault_path": "note.md"},
        nodes=stack["nodes"],
        vec=stack["vec"],
        bus=stack["bus"],
        embedder=stack["embedder"],
    )
    await asyncio.sleep(0.01)

    assert first.id == second.id
    rows = stack["nodes"].conn.query(
        "MATCH (t:Thought) WHERE t.content = $c RETURN count(t) AS n",
        {"c": "hello world"},
    )
    assert rows[0]["n"] == 1
    # Second capture is a no-op on the event bus
    assert len(thought_events) == 1
    assert len(graph_events) == 1


@pytest.mark.asyncio
async def test_normalize_does_not_dedup_across_sources(stack):
    """Same content from two different sources keeps both — capturing the
    same idea via CLI and via Obsidian are different signals.
    """
    a = await normalize_and_persist(
        content="same body",
        source="cli",
        metadata={},
        nodes=stack["nodes"],
        vec=stack["vec"],
        bus=stack["bus"],
        embedder=stack["embedder"],
    )
    b = await normalize_and_persist(
        content="same body",
        source="obsidian",
        metadata={},
        nodes=stack["nodes"],
        vec=stack["vec"],
        bus=stack["bus"],
        embedder=stack["embedder"],
    )
    await asyncio.sleep(0.01)
    assert a.id != b.id


@pytest.mark.asyncio
async def test_normalize_creates_new_when_content_differs(stack):
    a = await normalize_and_persist(
        content="first body",
        source="cli",
        metadata={},
        nodes=stack["nodes"],
        vec=stack["vec"],
        bus=stack["bus"],
        embedder=stack["embedder"],
    )
    b = await normalize_and_persist(
        content="second body",
        source="cli",
        metadata={},
        nodes=stack["nodes"],
        vec=stack["vec"],
        bus=stack["bus"],
        embedder=stack["embedder"],
    )
    await asyncio.sleep(0.01)
    assert a.id != b.id
