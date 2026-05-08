from fastapi import APIRouter, Query

from app.db.kuzu import KuzuConnection

# Tables we expose to the brain view (Agent excluded — agents have their own /agents endpoint)
_GRAPH_TABLES = [
    "Thought",
    "Bet",
    "Task",
    "Decision",
    "Conflict",
    "Outcome",
    "AgentFiring",
    "CodeChange",
    "Conversation",
    "Doc",
    "GateItem",
]

# Some tables use a non-standard timestamp column name (matches NodeRepository._FIELD_REMAP).
_TIMESTAMP_COLUMN: dict[str, str] = {
    "Decision": "decided_at",
    "Conflict": "detected_at",
    "Outcome": "recorded_at",
    "Doc": "updated_at",
    "AgentFiring": "started_at",
}


def build_graph_router(*, conn: KuzuConnection) -> APIRouter:
    router = APIRouter()

    @router.get("/graph")
    def get_graph(
        types: str | None = Query(
            default=None, description="Comma-separated node types to include"
        ),
        limit: int = Query(default=2000, ge=1, le=10000),
    ) -> dict:
        included = types.split(",") if types else _GRAPH_TABLES
        included = [t for t in included if t in _GRAPH_TABLES]

        all_nodes: list[dict] = []
        for table in included:
            ts_col = _TIMESTAMP_COLUMN.get(table, "created_at")
            rows = conn.query(
                f"MATCH (n:{table}) RETURN n.id AS id, "
                f"n.{ts_col} AS created_at LIMIT $limit",
                {"limit": limit},
            )
            for row in rows:
                all_nodes.append(
                    {
                        "id": row["id"],
                        "type": table,
                        "created_at": str(row.get("created_at", "")),
                    }
                )

        edges = conn.query(
            "MATCH (a)-[r:REL]->(b) "
            "RETURN a.id AS from_id, b.id AS to_id, "
            "r.edge_type AS edge_type, r.created_at AS created_at "
            "LIMIT $limit",
            {"limit": limit * 4},
        )
        edge_list = [
            {
                "from_id": e["from_id"],
                "to_id": e["to_id"],
                "edge_type": e["edge_type"],
                "created_at": str(e.get("created_at", "")),
            }
            for e in edges
        ]
        return {"nodes": all_nodes, "edges": edge_list}

    return router
