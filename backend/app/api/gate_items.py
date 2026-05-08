from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.events.bus import EventBus

_URGENCY_ORDER = {"urgent": 0, "high": 1, "medium": 2, "novel": 3, "low": 4}


class ResolveRequest(BaseModel):
    decision: Literal["approved", "vetoed", "resteered"]
    reasoning: str = ""
    alternative: dict | None = None


def build_gate_items_router(
    *,
    nodes: NodeRepository,
    conn: KuzuConnection,
    bus: EventBus,
) -> APIRouter:
    router = APIRouter()

    @router.get("/gate-items")
    def list_gate_items() -> list[dict]:
        rows = conn.query(
            "MATCH (g:GateItem) WHERE g.resolved_at IS NULL "
            "RETURN g.id AS id, g.prompt AS prompt, g.urgency AS urgency, "
            "g.created_at AS created_at"
        )
        rows.sort(key=lambda r: _URGENCY_ORDER.get(r.get("urgency"), 99))
        return [
            {
                "id": r["id"],
                "prompt": r["prompt"],
                "urgency": r.get("urgency"),
                "created_at": str(r.get("created_at", "")),
            }
            for r in rows
        ]

    @router.post("/gate-items/{gate_id}/resolve")
    async def resolve(gate_id: str, req: ResolveRequest) -> dict:
        now = datetime.now(timezone.utc)
        # Atomic compare-and-set: only update rows that exist AND aren't yet
        # resolved. The RETURN tells us whether a row was actually mutated.
        updated = conn.query(
            "MATCH (g:GateItem) WHERE g.id = $id AND g.resolved_at IS NULL "
            "SET g.resolved_at = $resolved_at, g.decision = $decision, "
            "g.reasoning = $reasoning "
            "RETURN g.id AS id",
            {
                "id": gate_id,
                "resolved_at": now,
                "decision": req.decision,
                "reasoning": req.reasoning,
            },
        )
        if not updated:
            # Either the node didn't exist, or it was already resolved.
            # Disambiguate with a follow-up read (rare path).
            if nodes.get(gate_id, "GateItem") is None:
                raise HTTPException(
                    status_code=404, detail=f"gate item {gate_id} not found"
                )
            raise HTTPException(status_code=409, detail="gate item already resolved")
        # GigaFlow event emission is intentionally deferred to Plan 6.
        # For Plan 3, resolving just mutates the graph node.
        return {"id": gate_id, "decision": req.decision, "resolved_at": str(now)}

    return router
