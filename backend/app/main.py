import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.api import health
from app.api.stream import make_event_generator
from app.capture.api import CaptureRequest, CaptureResponse
from app.capture.normalizer import normalize_and_persist
from app.config import GigaBrainConfig, load_config
from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.embeddings.factory import build_provider
from app.events.bus import EventBus
from app.sparring.engine import SparringEngine
from app.telemetry.otel import setup_otel

log = logging.getLogger(__name__)


def _load_active_config() -> GigaBrainConfig:
    path = os.environ.get("GIGABRAIN_CONFIG", "gigabrain.yaml")
    if not Path(path).exists():
        return GigaBrainConfig()
    return load_config(path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = _load_active_config()
    setup_otel(otlp_endpoint=cfg.telemetry.otlp_endpoint)

    conn = KuzuConnection(cfg.db.kuzu_path)
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[1] / "kuzu_schema")

    nodes = NodeRepository(conn)
    edges = EdgeRepository(conn)
    embedder = build_provider(cfg.embeddings)
    vec = VectorStore(cfg.db.vector_path, dim=embedder.dim)
    vec.connect()
    bus = EventBus()

    engine = SparringEngine(
        cfg=cfg.llm,
        nodes=nodes,
        edges=edges,
        vec=vec,
        bus=bus,
        embedder=embedder,
    )
    engine.attach()

    app.state.cfg = cfg
    app.state.nodes = nodes
    app.state.edges = edges
    app.state.vec = vec
    app.state.bus = bus
    app.state.embedder = embedder

    yield

    vec.close()
    conn.close()


app = FastAPI(title="GigaBrain", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)


@app.post("/capture", response_model=CaptureResponse)
async def capture(req: CaptureRequest, request: Request):
    try:
        state = request.app.state
        thought = await normalize_and_persist(
            content=req.content,
            source=req.source,
            metadata=req.metadata,
            nodes=state.nodes,
            vec=state.vec,
            bus=state.bus,
            embedder=state.embedder,
        )
        return CaptureResponse(node_id=thought.id, status="sparring")
    except Exception:
        log.exception("capture failed")
        return JSONResponse(status_code=500, content={"detail": "internal error"})


@app.get("/stream")
async def stream(request: Request):
    try:
        bus: EventBus = request.app.state.bus
    except AttributeError:
        return JSONResponse(status_code=500, content={"detail": "not ready"})
    _queue, generator = make_event_generator(bus)
    return StreamingResponse(generator, media_type="text/event-stream")
