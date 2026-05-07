import asyncio
from pathlib import Path

import pytest

from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import ThoughtNode
from app.events.bus import EventBus
from app.events.schemas import GateItemCreated
from app.sparring.llm import SparringResult
from app.sparring.router import route_sparring_result


@pytest.mark.asyncio
async def test_conflict_classification_creates_edge_and_emits_event(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    edges = EdgeRepository(conn)
    bus = EventBus()

    received = []

    async def handler(event: GateItemCreated):
        received.append(event)

    bus.subscribe("gate.created", handler)

    # Pre-existing thought to attach the gate item to
    thought = ThoughtNode(content="some thought", source="cli")
    nodes.create(thought)

    result = SparringResult(
        classification="conflict",
        reasoning="contradicts something",
        edges_to_record=[],  # no proposed edges, just the conflict signal
    )
    await route_sparring_result(
        result=result,
        thought_id=thought.id,
        nodes=nodes,
        edges=edges,
        bus=bus,
    )
    await asyncio.sleep(0.05)

    # Gate item was created
    gates = conn.query("MATCH (g:GateItem) RETURN g.id AS id")
    assert len(gates) == 1
    gate_id = gates[0]["id"]

    # Edge from thought to gate item exists (Thought -[led-to]-> GateItem)
    outgoing = edges.list_outgoing(thought.id, "Thought")
    led_to_edges = [e for e in outgoing if e["edge_type"] == "led-to"]
    assert len(led_to_edges) == 1
    assert led_to_edges[0]["to_id"] == gate_id

    # GateItemCreated event was published
    assert len(received) == 1
    assert received[0].gate_item_id == gate_id

    conn.close()
