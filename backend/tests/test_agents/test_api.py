from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.api import build_agents_router
from app.agents.config import AgentSpec, DispatchConfig, FleetConfig
from app.agents.dispatcher import Dispatcher
from app.agents.registry import AgentRegistry
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository


@pytest.fixture
def configured_app(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    reg = AgentRegistry(nodes=nodes, conn=conn)
    reg.sync(
        FleetConfig(
            agents=[
                AgentSpec(id="eng-1", role="engineer", persona="x"),
            ]
        )
    )
    dispatcher = Dispatcher(cfg=DispatchConfig(max_parallel=2))
    app = FastAPI()
    app.include_router(
        build_agents_router(registry=reg, conn=conn, dispatcher=dispatcher)
    )
    yield app
    conn.close()


@pytest.fixture
def client_with_dispatcher(tmp_path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    registry = AgentRegistry(nodes=nodes, conn=conn)
    dispatcher = Dispatcher(cfg=DispatchConfig(max_parallel=2))
    app = FastAPI()
    app.include_router(
        build_agents_router(registry=registry, conn=conn, dispatcher=dispatcher)
    )
    yield TestClient(app), dispatcher
    conn.close()


def test_list_agents(configured_app):
    client = TestClient(configured_app)
    resp = client.get("/agents")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == "eng-1"


def test_pause_and_resume(configured_app):
    client = TestClient(configured_app)
    r1 = client.post("/agents/eng-1/pause")
    assert r1.status_code == 200

    body = client.get("/agents").json()
    assert body[0]["state"] == "paused"

    client.post("/agents/eng-1/resume")
    body = client.get("/agents").json()
    assert body[0]["state"] == "idle"


def test_pause_unknown_agent_returns_404(configured_app):
    client = TestClient(configured_app)
    resp = client.post("/agents/missing/pause")
    assert resp.status_code == 404


def test_inflight_returns_empty_when_idle(client_with_dispatcher):
    client, _ = client_with_dispatcher
    r = client.get("/agents/inflight")
    assert r.status_code == 200
    assert r.json() == []


def test_inflight_returns_running_firings(client_with_dispatcher):
    client, dispatcher = client_with_dispatcher
    # Inject a fake in-flight entry (test-only — production fills it via dispatch)
    dispatcher._inflight["fid-X"] = {
        "firing_id": "fid-X",
        "role": "cto",
        "started_at": 1234567890.0,
    }
    try:
        r = client.get("/agents/inflight")
        assert r.status_code == 200
        body = r.json()
        assert body == [
            {"firing_id": "fid-X", "role": "cto", "started_at": 1234567890.0}
        ]
    finally:
        dispatcher._inflight.pop("fid-X", None)
