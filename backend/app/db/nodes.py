import json

from app.db.kuzu import KuzuConnection
from app.db.schemas import (
    AgentFiringNode,
    AgentNode,
    BetNode,
    CodeChangeNode,
    ConflictNode,
    ConversationNode,
    DecisionNode,
    DocNode,
    GateItemNode,
    OutcomeNode,
    TaskNode,
    ThoughtNode,
)

_NODE_TABLES: dict[type, str] = {
    ThoughtNode: "Thought",
    BetNode: "Bet",
    TaskNode: "Task",
    DecisionNode: "Decision",
    ConflictNode: "Conflict",
    OutcomeNode: "Outcome",
    AgentFiringNode: "AgentFiring",
    CodeChangeNode: "CodeChange",
    ConversationNode: "Conversation",
    DocNode: "Doc",
    GateItemNode: "GateItem",
    AgentNode: "Agent",
}

# Some Pydantic models use `created_at` but the Kuzu schema uses a different
# timestamp column name.  Map (node_type -> {pydantic_field: kuzu_column}).
_FIELD_REMAP: dict[type, dict[str, str]] = {
    DecisionNode: {"created_at": "decided_at"},
    ConflictNode: {"created_at": "detected_at"},
    OutcomeNode: {"created_at": "recorded_at"},
    DocNode: {"created_at": "updated_at"},
}

# Fields that exist in the Pydantic model but have no corresponding column in
# the Kuzu table (beyond the universal `node_type` exclusion).
_EXTRA_EXCLUDE: dict[type, set[str]] = {
    # Agent table has no created_at column at all
    AgentNode: {"created_at"},
}


class NodeRepository:
    def __init__(self, conn: KuzuConnection):
        self.conn = conn

    def create(self, node) -> None:
        table = _NODE_TABLES[type(node)]
        # Exclude node_type — Kuzu tables don't have that column; the table
        # name itself encodes the type.
        extra_exclude = _EXTRA_EXCLUDE.get(type(node), set())
        data = node.model_dump(exclude={"node_type"} | extra_exclude)

        # Convert metadata dict (Thought) to JSON string for Kuzu STRING column
        if "metadata" in data and isinstance(data["metadata"], dict):
            data["metadata"] = json.dumps(data["metadata"])

        # Rename fields whose Pydantic name differs from the Kuzu column name
        remap = _FIELD_REMAP.get(type(node), {})
        for pydantic_field, kuzu_col in remap.items():
            if pydantic_field in data:
                data[kuzu_col] = data.pop(pydantic_field)

        cols = list(data.keys())
        cypher = f"CREATE (:{table} {{{', '.join(f'{c}: ${c}' for c in cols)}}})"
        self.conn.query(cypher, data)

    def get(self, node_id: str, table: str) -> dict | None:
        cypher = f"MATCH (n:{table}) WHERE n.id = $id RETURN n"
        result = self.conn.query(cypher, {"id": node_id})
        if not result:
            return None
        # Kuzu returns the node properties as a dict under the column name "n"
        row = result[0]
        node_dict = row["n"] if isinstance(row.get("n"), dict) else row
        return node_dict
