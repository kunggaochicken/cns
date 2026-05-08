import asyncio
from pathlib import Path

import pytest

from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import DecisionNode, ThoughtNode
from app.events.bus import EventBus
from app.events.schemas import GateItemCreated
from app.sparring.llm import SparringEdge, SparringResult
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
        conn=conn,
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


@pytest.mark.asyncio
async def test_router_records_edges_to_non_bet_targets(tmp_path: Path):
    """Edges to Decision, Conflict, etc. must not be silently dropped."""
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    edges = EdgeRepository(conn)
    bus = EventBus()

    thought = ThoughtNode(content="...", source="cli")
    decision = DecisionNode(content="prior decision", decided_by="cto")
    nodes.create(thought)
    nodes.create(decision)

    result = SparringResult(
        classification="clear",
        reasoning="aligns with prior decision",
        edges_to_record=[
            SparringEdge(
                target_id=decision.id, edge_type="aligns-with", confidence=0.9
            ),
        ],
    )
    await route_sparring_result(
        result=result,
        thought_id=thought.id,
        nodes=nodes,
        edges=edges,
        bus=bus,
        conn=conn,
    )

    outgoing = edges.list_outgoing(thought.id, "Thought")
    aligns = [e for e in outgoing if e["edge_type"] == "aligns-with"]
    assert len(aligns) == 1
    assert aligns[0]["to_id"] == decision.id
    conn.close()
