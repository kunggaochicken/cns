from fastapi import APIRouter, HTTPException

from app.db.kuzu import KuzuConnection


_TABLE_TO_TYPE = {
    "Thought": "thought",
    "Bet": "bet",
    "Task": "task",
    "Decision": "decision",
    "Conflict": "conflict",
    "Outcome": "outcome",
    "AgentFiring": "agent_firing",
    "CodeChange": "code_change",
    "Conversation": "conversation",
    "Doc": "doc",
    "GateItem": "gate_item",
    "Agent": "agent",
}


def _normalize_node(payload: dict, node_type: str) -> dict:
    out = dict(payload)
    out["node_type"] = node_type
    for ts in (
        "created_at",
        "started_at",
        "completed_at",
        "resolved_at",
        "decided_at",
        "detected_at",
        "recorded_at",
        "updated_at",
        "last_active",
    ):
        if ts in out and out[ts] is not None and not isinstance(out[ts], str):
            out[ts] = out[ts].isoformat()
    return out


def build_graph_router(conn: KuzuConnection) -> APIRouter:
    router = APIRouter(prefix="/graph")

    @router.get("/state")
    async def state():
        nodes: list[dict] = []
        for table, node_type in _TABLE_TO_TYPE.items():
            rows = conn.query(f"MATCH (n:{table}) RETURN n")
            for row in rows:
                raw = row["n"] if isinstance(row.get("n"), dict) else row
                nodes.append(_normalize_node(raw, node_type))

        edge_rows = conn.query(
            "MATCH (a)-[e:REL]->(b) "
            "RETURN a.id AS from_id, b.id AS to_id, "
            "e.edge_type AS edge_type, e.created_at AS created_at, "
            "e.confidence AS confidence"
        )
        edges = []
        for r in edge_rows:
            created_at = r.get("created_at")
            if created_at is not None and not isinstance(created_at, str):
                created_at = created_at.isoformat()
            conf = r.get("confidence")
            confidence = conf if conf is not None else 1.0
            edges.append(
                {
                    "from_id": r["from_id"],
                    "from_type": None,
                    "to_id": r["to_id"],
                    "to_type": None,
                    "edge_type": r.get("edge_type") or "rel",
                    "created_at": created_at,
                    "confidence": confidence,
                }
            )
        return {"nodes": nodes, "edges": edges}

    @router.get("/nodes/{node_id}")
    async def node_detail(node_id: str):
        for table, node_type in _TABLE_TO_TYPE.items():
            rows = conn.query(
                f"MATCH (n:{table}) WHERE n.id = $id RETURN n",
                {"id": node_id},
            )
            if rows:
                raw = rows[0]["n"] if isinstance(rows[0].get("n"), dict) else rows[0]
                payload = _normalize_node(raw, node_type)
                payload["edges_in"] = conn.query(
                    "MATCH (a)-[e:REL]->(b) WHERE b.id = $id "
                    "RETURN a.id AS from_id, e.edge_type AS edge_type",
                    {"id": node_id},
                )
                payload["edges_out"] = conn.query(
                    "MATCH (a)-[e:REL]->(b) WHERE a.id = $id "
                    "RETURN b.id AS to_id, e.edge_type AS edge_type",
                    {"id": node_id},
                )
                return payload
        raise HTTPException(status_code=404, detail=f"node {node_id} not found")

    return router
