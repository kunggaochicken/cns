from fastapi import APIRouter, HTTPException

from app.agents.dispatcher import Dispatcher
from app.agents.registry import AgentRegistry
from app.db.kuzu import KuzuConnection


def build_agents_router(
    *,
    registry: AgentRegistry,
    conn: KuzuConnection,
    dispatcher: Dispatcher,
) -> APIRouter:
    router = APIRouter()

    @router.get("/agents")
    def list_agents() -> list[dict]:
        return registry.list_agents()

    @router.get("/agents/inflight")
    def inflight() -> list[dict]:
        return dispatcher.in_flight()

    @router.post("/agents/{agent_id}/pause")
    def pause(agent_id: str) -> dict:
        if registry.get_by_id(agent_id) is None:
            raise HTTPException(status_code=404, detail=f"agent {agent_id} not found")
        conn.query(
            "MATCH (a:Agent) WHERE a.id = $id SET a.state = 'paused'",
            {"id": agent_id},
        )
        return {"id": agent_id, "state": "paused"}

    @router.post("/agents/{agent_id}/resume")
    def resume(agent_id: str) -> dict:
        if registry.get_by_id(agent_id) is None:
            raise HTTPException(status_code=404, detail=f"agent {agent_id} not found")
        conn.query(
            "MATCH (a:Agent) WHERE a.id = $id SET a.state = 'idle'",
            {"id": agent_id},
        )
        return {"id": agent_id, "state": "idle"}

    return router
