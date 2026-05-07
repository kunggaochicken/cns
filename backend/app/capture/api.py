from fastapi import APIRouter
from pydantic import BaseModel

from app.capture.normalizer import normalize_and_persist
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.embeddings.provider import EmbeddingsProvider
from app.events.bus import EventBus


class CaptureRequest(BaseModel):
    content: str
    source: str = "web"
    metadata: dict = {}


class CaptureResponse(BaseModel):
    node_id: str
    status: str


def build_capture_router(
    *,
    nodes: NodeRepository,
    vec: VectorStore,
    bus: EventBus,
    embedder: EmbeddingsProvider,
) -> APIRouter:
    router = APIRouter()

    @router.post("/capture", response_model=CaptureResponse)
    async def capture(req: CaptureRequest):
        thought = await normalize_and_persist(
            content=req.content,
            source=req.source,
            metadata=req.metadata,
            nodes=nodes,
            vec=vec,
            bus=bus,
            embedder=embedder,
        )
        return CaptureResponse(node_id=thought.id, status="sparring")

    return router
