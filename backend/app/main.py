import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api import health
from app.api.stream import build_stream_router
from app.capture.api import build_capture_router
from app.config import GigaBrainConfig, load_config
from app.gate.api import build_gate_router
from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.embeddings.factory import build_provider
from app.events.bus import EventBus
from app.sparring.engine import SparringEngine
from app.telemetry.otel import setup_otel

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


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
        detectors_cfg=cfg.detectors,
        conn=conn,
        nodes=nodes,
        edges=edges,
        vec=vec,
        bus=bus,
        embedder=embedder,
        vault_path=cfg.agents.vault_path,
    )
    engine.attach()

    from app.agents.config import FleetConfig, load_fleet_config
    from app.agents.dispatcher import Dispatcher
    from app.agents.registry import AgentRegistry
    from app.agents.worker import AgentWorker

    fleet_path = Path(cfg.agents.yaml_path)
    fleet = load_fleet_config(fleet_path) if fleet_path.exists() else FleetConfig()
    registry = AgentRegistry(nodes=nodes, conn=conn)
    registry.sync(fleet)
    dispatcher = Dispatcher(cfg=fleet.dispatch, bus=bus)
    worker = AgentWorker(
        registry=registry,
        nodes=nodes,
        edges=edges,
        bus=bus,
        llm_cfg=cfg.llm,
        fleet=fleet,
        vault_path=cfg.agents.vault_path,
        repo_path=cfg.agents.repo_path,
        dispatcher=dispatcher,
    )
    worker.attach()
    app.state.dispatcher = dispatcher
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
    app.include_router(build_gate_router(conn, bus))

    from app.api.graph import build_graph_router

    app.include_router(build_graph_router(conn))

    from app.api.webhooks.linear import build_linear_webhook_router

    linear_secret = (
        os.environ.get(cfg.webhooks.linear_secret_env)
        if cfg.webhooks.linear_secret_env
        else None
    )
    app.include_router(
        build_linear_webhook_router(
            nodes=nodes, vec=vec, bus=bus, embedder=embedder, secret=linear_secret
        )
    )

    from app.api.webhooks.github import build_github_webhook_router

    github_secret = (
        os.environ.get(cfg.webhooks.github_secret_env)
        if cfg.webhooks.github_secret_env
        else None
    )
    app.include_router(
        build_github_webhook_router(
            nodes=nodes, vec=vec, bus=bus, embedder=embedder, secret=github_secret
        )
    )

    from app.agents.api import build_agents_router

    app.include_router(
        build_agents_router(registry=registry, conn=conn, dispatcher=dispatcher)
    )

    from app.api.frontend import mount_frontend

    mount_frontend(app)

    from app.watchers.obsidian import ObsidianWatcher

    obsidian_cfg = cfg.watchers.obsidian
    if obsidian_cfg.enabled and Path(cfg.agents.vault_path).exists():
        watcher = ObsidianWatcher(
            vault=Path(cfg.agents.vault_path),
            nodes=nodes,
            vec=vec,
            bus=bus,
            embedder=embedder,
            debounce_seconds=obsidian_cfg.debounce_seconds,
            ignore_patterns=obsidian_cfg.ignore_patterns,
        )
        app.state.obsidian_watcher_task = asyncio.create_task(watcher.run())
    else:
        app.state.obsidian_watcher_task = None

    yield

    if app.state.obsidian_watcher_task is not None:
        app.state.obsidian_watcher_task.cancel()
        try:
            await app.state.obsidian_watcher_task
        except (asyncio.CancelledError, Exception):
            pass

    vec.close()
    conn.close()


app = FastAPI(title="GigaBrain", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
