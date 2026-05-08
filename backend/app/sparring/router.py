import logging

from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import EdgeRecord, GateItemNode, NodeType
from app.events.bus import EventBus
from app.events.schemas import FireNeuron, GateItemCreated
from app.sparring.llm import SparringResult

log = logging.getLogger(__name__)

_ALL_TABLES = [
    ("Thought", NodeType.THOUGHT),
    ("Bet", NodeType.BET),
    ("Task", NodeType.TASK),
    ("Decision", NodeType.DECISION),
    ("Conflict", NodeType.CONFLICT),
    ("Outcome", NodeType.OUTCOME),
    ("AgentFiring", NodeType.AGENT_FIRING),
    ("CodeChange", NodeType.CODE_CHANGE),
    ("Conversation", NodeType.CONVERSATION),
    ("Doc", NodeType.DOC),
    ("GateItem", NodeType.GATE_ITEM),
    ("Agent", NodeType.AGENT),
]


def _lookup_node_type(conn: KuzuConnection, node_id: str) -> NodeType | None:
    """Probe each Kuzu node table to find which one owns *node_id*."""
    for table, ntype in _ALL_TABLES:
        rows = conn.query(
            f"MATCH (n:{table}) WHERE n.id = $id RETURN n.id AS id LIMIT 1",
            {"id": node_id},
        )
        if rows:
            return ntype
    return None


async def route_sparring_result(
    *,
    result: SparringResult,
    thought_id: str,
    nodes: NodeRepository,
    edges: EdgeRepository,
    bus: EventBus,
    conn: KuzuConnection,
) -> None:
    # Write proposed edges, resolving the actual target node type via Kuzu lookup.
    for e in result.edges_to_record:
        to_type = _lookup_node_type(conn, e.target_id)
        if to_type is None:
            log.warning(
                "route_sparring_result: target node %s not found in any table; "
                "dropping edge %s -> %s",
                e.target_id,
                thought_id,
                e.target_id,
            )
            continue
        edges.create(
            EdgeRecord(
                from_id=thought_id,
                from_type=NodeType.THOUGHT,
                to_id=e.target_id,
                to_type=to_type,
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
                from_id=thought_id,
                from_type=NodeType.THOUGHT,
                to_id=gate.id,
                to_type=NodeType.GATE_ITEM,
                edge_type="led-to",
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
