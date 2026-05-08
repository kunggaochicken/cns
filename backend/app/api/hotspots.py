from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from app.db.kuzu import KuzuConnection

# Same set as graph router; keep in sync (followup: centralize)
_TABLES = (
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
)


def build_hotspots_router(*, conn: KuzuConnection) -> APIRouter:
    router = APIRouter()

    @router.get("/hotspots")
    def hotspots(
        within_hours: int = Query(default=1, ge=1, le=168),
        limit: int = Query(default=10, ge=1, le=100),
    ) -> list[dict]:
        threshold = datetime.now(timezone.utc) - timedelta(hours=within_hours)
        # Per-table UNION: Kuzu's label() function is unreliable across versions.
        # See app/sparring/retrieval.py for the same pattern.
        counts: dict[tuple[str, str], int] = {}
        for table in _TABLES:
            # Outgoing edges from this table
            out_rows = conn.query(
                f"MATCH (a:{table})-[r:REL]->(b) WHERE r.created_at > $threshold "
                "RETURN a.id AS node_id",
                {"threshold": threshold},
            )
            for row in out_rows:
                key = (row["node_id"], table)
                counts[key] = counts.get(key, 0) + 1
            # Incoming edges to this table
            in_rows = conn.query(
                f"MATCH (a)-[r:REL]->(b:{table}) WHERE r.created_at > $threshold "
                "RETURN b.id AS node_id",
                {"threshold": threshold},
            )
            for row in in_rows:
                key = (row["node_id"], table)
                counts[key] = counts.get(key, 0) + 1

        ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
        return [{"id": k[0], "type": k[1], "edge_count": v} for k, v in ranked]

    return router
