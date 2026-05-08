from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.api import build_agents_router
from app.agents.config import AgentSpec, FleetConfig
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
    app = FastAPI()
    app.include_router(build_agents_router(registry=reg, conn=conn))
    yield app
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
