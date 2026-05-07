from app.db.edges import EdgeRepository
from app.db.nodes import NodeRepository
from app.db.schemas import EdgeRecord, GateItemNode, NodeType
from app.events.bus import EventBus
from app.events.schemas import FireNeuron, GateItemCreated
from app.sparring.llm import SparringResult


async def route_sparring_result(
    *,
    result: SparringResult,
    thought_id: str,
    nodes: NodeRepository,
    edges: EdgeRepository,
    bus: EventBus,
) -> None:
    # Always: write the proposed edges. We default to_type=BET for the simple case;
    # callers that know the actual to_type can pre-filter or override.
    for e in result.edges_to_record:
        edges.create(
            EdgeRecord(
                from_id=thought_id,
                from_type=NodeType.THOUGHT,
                to_id=e.target_id,
                to_type=NodeType.BET,
                edge_type=e.edge_type,
                confidence=e.confidence,
            )
        )

    if result.classification == "clear" and result.suggested_action:
        await bus.publish(
            FireNeuron(
                thought_id=thought_id,
                agent_role=result.suggested_action.agent_role,
                task_summary=result.suggested_action.task_summary,
            )
        )
    elif result.classification == "conflict":
        gate = GateItemNode(
            prompt=f"Sparring flagged conflict: {result.reasoning}",
            urgency="medium",
        )
        nodes.create(gate)
        edges.create(
            EdgeRecord(
                from_id=gate.id,
                from_type=NodeType.GATE_ITEM,
                to_id=thought_id,
                to_type=NodeType.THOUGHT,
                edge_type="resolved-by",
                confidence=1.0,
            )
        )
        await bus.publish(
            GateItemCreated(
                gate_item_id=gate.id,
                thought_id=thought_id,
                urgency=gate.urgency,
            )
        )
    # `novel`: no further action; thought stays indexed
