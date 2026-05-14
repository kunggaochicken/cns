from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.schemas import GateItemNode
from app.events.schemas import FireNeuron, GateItemCreated, GraphChanged
from app.sparring.llm import SparringEdge, SparringResult, SuggestedAction
from app.sparring.router import route_sparring_result


def _make_conn_mock(known_ids: set[str]):
    """Return a KuzuConnection mock whose .query() resolves known node IDs as Bet."""
    conn = MagicMock()

    def _query(cypher, params=None):
        node_id = (params or {}).get("id", "")
        # Pretend the node lives in the Bet table if its ID is in known_ids
        if node_id in known_ids:
            return [{"id": node_id}]
        return []

    conn.query.side_effect = _query
    return conn


@pytest.mark.asyncio
async def test_clear_actionable_emits_fire_neuron():
    nodes = AsyncMock()
    edges = AsyncMock()
    bus = AsyncMock()
    conn = _make_conn_mock({"b_1"})
    result = SparringResult(
        classification="clear",
        reasoning="aligns with engineer queue",
        edges_to_record=[
            SparringEdge(target_id="b_1", edge_type="aligns-with", confidence=0.9)
        ],
        suggested_action=SuggestedAction(
            agent_role="engineer", task_summary="add /capture endpoint"
        ),
    )
    await route_sparring_result(
        result=result,
        thought_id="t_1",
        nodes=nodes,
        edges=edges,
        bus=bus,
        conn=conn,
    )
    bus.publish.assert_called_once()
    published = bus.publish.call_args.args[0]
    assert isinstance(published, FireNeuron)
    assert published.agent_role == "engineer"


@pytest.mark.asyncio
async def test_conflict_creates_gate_item():
    nodes = AsyncMock()
    edges = AsyncMock()
    bus = AsyncMock()
    conn = _make_conn_mock({"b_auth"})
    result = SparringResult(
        classification="conflict",
        reasoning="contradicts b_auth_pivot",
        edges_to_record=[
            SparringEdge(target_id="b_auth", edge_type="contradicts", confidence=0.95)
        ],
    )
    await route_sparring_result(
        result=result,
        thought_id="t_1",
        nodes=nodes,
        edges=edges,
        bus=bus,
        conn=conn,
    )
    nodes.create.assert_called()
    created_node = nodes.create.call_args.args[0]
    assert isinstance(created_node, GateItemNode)
    published_events = [call.args[0] for call in bus.publish.call_args_list]
    gate_events = [e for e in published_events if isinstance(e, GateItemCreated)]
    graph_events = [e for e in published_events if isinstance(e, GraphChanged)]
    assert len(gate_events) == 1
    assert len(graph_events) == 1
    assert graph_events[0].change_type == "node_created"
    assert graph_events[0].node_id == created_node.id
