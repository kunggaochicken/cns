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
    AgentFiringNode: {"created_at"},  # uses started_at/completed_at instead
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

    def find_thought_by_hash(self, content_hash: str, source: str) -> dict | None:
        """Look up a Thought by (content_hash, source). Returns the node
        dict (with metadata decoded back to dict) or None. Used by the
        capture normalizer to dedup re-captures.
        """
        if not content_hash:
            return None
        cypher = (
            "MATCH (t:Thought) WHERE t.content_hash = $h AND t.source = $s "
            "RETURN t LIMIT 1"
        )
        result = self.conn.query(cypher, {"h": content_hash, "s": source})
        if not result:
            return None
        row = result[0]
        node = row["t"] if isinstance(row.get("t"), dict) else row
        # Kuzu stores metadata as a JSON string (see create()); decode it back.
        meta = node.get("metadata")
        if isinstance(meta, str):
            try:
                node["metadata"] = json.loads(meta) if meta else {}
            except json.JSONDecodeError:
                node["metadata"] = {}
        return node
