from fastapi import APIRouter, HTTPException

from app.db.kuzu import KuzuConnection
from app.events.bus import EventBus
from app.events.schemas import GraphChanged
from app.gate.resolver import GateResolveRequest, resolve_gate_item


def build_gate_router(conn: KuzuConnection, bus: EventBus) -> APIRouter:
    router = APIRouter(prefix="/gate")

    @router.post("/{gate_id}/resolve")
    async def resolve(gate_id: str, req: GateResolveRequest):
        alternative = (req.alternative or "").strip() or None
        if alternative is not None and req.decision != "resteered":
            raise HTTPException(
                status_code=422,
                detail="alternative only valid when decision='resteered'",
            )

        ok = resolve_gate_item(conn, gate_id, req)
        if not ok:
            raise HTTPException(status_code=404, detail=f"gate {gate_id} not found")

        extra = {"alternative": alternative} if alternative is not None else None
        await bus.publish(
            GraphChanged(change_type="node_updated", node_id=gate_id, extra=extra)
        )

        response: dict = {"status": "ok"}
        if alternative is not None:
            response["alternative"] = alternative
        return response

    return router
