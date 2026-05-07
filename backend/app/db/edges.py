from app.db.kuzu import KuzuConnection
from app.db.schemas import EdgeRecord, NodeType

_TYPE_TO_TABLE: dict[NodeType, str] = {
    NodeType.THOUGHT: "Thought",
    NodeType.BET: "Bet",
    NodeType.TASK: "Task",
    NodeType.DECISION: "Decision",
    NodeType.CONFLICT: "Conflict",
    NodeType.OUTCOME: "Outcome",
    NodeType.AGENT_FIRING: "AgentFiring",
    NodeType.CODE_CHANGE: "CodeChange",
    NodeType.CONVERSATION: "Conversation",
    NodeType.DOC: "Doc",
    NodeType.GATE_ITEM: "GateItem",
    NodeType.AGENT: "Agent",
}


class EdgeRepository:
    def __init__(self, conn: KuzuConnection):
        self.conn = conn

    def create(self, edge: EdgeRecord) -> None:
        from_table = _TYPE_TO_TABLE[edge.from_type]
        to_table = _TYPE_TO_TABLE[edge.to_type]
        cypher = (
            f"MATCH (a:{from_table}), (b:{to_table}) "
            "WHERE a.id = $from_id AND b.id = $to_id "
            "CREATE (a)-[r:REL {edge_type: $edge_type, "
            "created_at: $created_at, confidence: $confidence}]->(b)"
        )
        self.conn.query(
            cypher,
            {
                "from_id": edge.from_id,
                "to_id": edge.to_id,
                "edge_type": edge.edge_type,
                "created_at": edge.created_at,
                "confidence": edge.confidence,
            },
        )

    def list_outgoing(self, node_id: str, table: str) -> list[dict]:
        cypher = (
            f"MATCH (a:{table})-[r:REL]->(b) WHERE a.id = $id "
            "RETURN r.edge_type AS edge_type, b.id AS to_id, "
            "r.confidence AS confidence, r.created_at AS created_at"
        )
        return self.conn.query(cypher, {"id": node_id})

    def list_incoming(self, node_id: str, table: str) -> list[dict]:
        cypher = (
            f"MATCH (a)-[r:REL]->(b:{table}) WHERE b.id = $id "
            "RETURN r.edge_type AS edge_type, a.id AS from_id, "
            "r.confidence AS confidence, r.created_at AS created_at"
        )
        return self.conn.query(cypher, {"id": node_id})
