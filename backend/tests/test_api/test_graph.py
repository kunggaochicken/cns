from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.graph import build_graph_router
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import BetNode, ThoughtNode


@pytest.fixture
def configured_app(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    nodes.create(BetNode(slug="auth", title="Auth", vault_path="x.md", owner="cto"))
    nodes.create(ThoughtNode(content="hi", source="cli"))
    app = FastAPI()
    app.include_router(build_graph_router(conn=conn))
    yield app
    conn.close()


def test_graph_returns_nodes_and_edges(configured_app):
    client = TestClient(configured_app)
    resp = client.get("/graph")
    assert resp.status_code == 200
    body = resp.json()
    assert "nodes" in body and "edges" in body
    assert len(body["nodes"]) == 2
    types = {n["type"] for n in body["nodes"]}
    assert {"Bet", "Thought"} <= types


def test_graph_filter_by_type(configured_app):
    client = TestClient(configured_app)
    resp = client.get("/graph?types=Bet")
    body = resp.json()
    assert all(n["type"] == "Bet" for n in body["nodes"])
