from unittest.mock import AsyncMock

import pytest

from app.db.schemas import GateItemNode
from app.events.schemas import FireNeuron, GateItemCreated
from app.sparring.llm import SparringEdge, SparringResult, SuggestedAction
from app.sparring.router import route_sparring_result


@pytest.mark.asyncio
async def test_clear_actionable_emits_fire_neuron():
    nodes = AsyncMock()
    edges = AsyncMock()
    bus = AsyncMock()
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
    )
    nodes.create.assert_called()
    created_node = nodes.create.call_args.args[0]
    assert isinstance(created_node, GateItemNode)
    published = bus.publish.call_args.args[0]
    assert isinstance(published, GateItemCreated)
