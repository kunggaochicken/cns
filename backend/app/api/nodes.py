from fastapi import APIRouter, HTTPException

from app.db.kuzu import KuzuConnection

_VALID_TABLES = {
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
    "Agent",
}


def build_nodes_router(*, conn: KuzuConnection) -> APIRouter:
    router = APIRouter()

    @router.get("/nodes/{table}/{node_id}")
    def get_node(table: str, node_id: str) -> dict:
        if table not in _VALID_TABLES:
            raise HTTPException(status_code=400, detail=f"unknown table: {table}")
        rows = conn.query(
            f"MATCH (n:{table}) WHERE n.id = $id RETURN n",
            {"id": node_id},
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"{table}/{node_id} not found")
        node = rows[0]["n"] if isinstance(rows[0].get("n"), dict) else rows[0]

        outgoing = conn.query(
            f"MATCH (a:{table})-[r:REL]->(b) WHERE a.id = $id "
            "RETURN r.edge_type AS edge_type, b.id AS to_id, "
            "r.confidence AS confidence",
            {"id": node_id},
        )
        incoming = conn.query(
            f"MATCH (a)-[r:REL]->(b:{table}) WHERE b.id = $id "
            "RETURN r.edge_type AS edge_type, a.id AS from_id, "
            "r.confidence AS confidence",
            {"id": node_id},
        )
        return {
            "id": node_id,
            "type": table,
            "props": {
                k: (
                    str(v)
                    if not isinstance(v, str | int | float | bool | type(None))
                    else v
                )
                for k, v in node.items()
            },
            "outgoing_edges": outgoing,
            "incoming_edges": incoming,
        }

    return router
