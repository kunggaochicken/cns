import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api import health
from app.api.graph import build_graph_router
from app.api.nodes import build_nodes_router
from app.api.stream import build_stream_router
from app.capture.api import build_capture_router
from app.config import GigaBrainConfig, load_config
from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.embeddings.factory import build_provider
from app.events.bus import EventBus
from app.sparring.engine import SparringEngine
from app.telemetry.otel import setup_otel


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

    from app.agents.config import FleetConfig, load_fleet_config
    from app.agents.registry import AgentRegistry
    from app.agents.worker import AgentWorker

    fleet_path = Path(cfg.agents.yaml_path)
    fleet = load_fleet_config(fleet_path) if fleet_path.exists() else FleetConfig()
    registry = AgentRegistry(nodes=nodes, conn=conn)
    registry.sync(fleet)
    worker = AgentWorker(
        registry=registry,
        nodes=nodes,
        edges=edges,
        bus=bus,
        llm_cfg=cfg.llm,
        fleet=fleet,
        vault_path=cfg.agents.vault_path,
        repo_path=cfg.agents.repo_path,
    )
    worker.attach()
    app.state.registry = registry
    app.state.worker = worker
    app.state.fleet = fleet

    app.state.cfg = cfg
    app.state.nodes = nodes
    app.state.edges = edges
    app.state.vec = vec
    app.state.bus = bus
    app.state.embedder = embedder

    # Include routers that need lifespan-built deps.
    # FastAPI's app.routes is live — dynamic include_router during lifespan works.
    app.include_router(
        build_capture_router(
            nodes=nodes,
            vec=vec,
            bus=bus,
            embedder=embedder,
        )
    )
    app.include_router(build_stream_router(bus))

    from app.agents.api import build_agents_router

    app.include_router(build_agents_router(registry=registry, conn=conn))
    app.include_router(build_graph_router(conn=conn))
    app.include_router(build_nodes_router(conn=conn, edges=edges))

    yield

    vec.close()
    conn.close()


app = FastAPI(title="GigaBrain", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
