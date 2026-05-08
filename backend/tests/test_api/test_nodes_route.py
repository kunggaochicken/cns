from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.nodes import build_nodes_router
from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import BetNode, EdgeRecord, NodeType, ThoughtNode


@pytest.fixture
def configured_app(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    edges = EdgeRepository(conn)
    bet = BetNode(slug="auth", title="Auth", vault_path="x.md", owner="cto")
    thought = ThoughtNode(content="related thought", source="cli")
    nodes.create(bet)
    nodes.create(thought)
    edges.create(
        EdgeRecord(
            from_id=thought.id,
            from_type=NodeType.THOUGHT,
            to_id=bet.id,
            to_type=NodeType.BET,
            edge_type="sparred-against",
        )
    )
    app = FastAPI()
    app.include_router(build_nodes_router(conn=conn, edges=edges))
    yield {"app": app, "bet": bet, "thought": thought}
    conn.close()


def test_get_node_returns_props_and_edges(configured_app):
    bet = configured_app["bet"]
    client = TestClient(configured_app["app"])
    resp = client.get(f"/nodes/Bet/{bet.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == bet.id
    assert body["type"] == "Bet"
    assert body["props"]["title"] == "Auth"
    # Incoming sparred-against edge from the thought
    assert any(e["edge_type"] == "sparred-against" for e in body["incoming_edges"])
    incoming = body["incoming_edges"][0]
    assert set(incoming.keys()) >= {"edge_type", "from_id", "confidence", "created_at"}


def test_get_unknown_node_returns_404(configured_app):
    client = TestClient(configured_app["app"])
    resp = client.get("/nodes/Bet/missing")
    assert resp.status_code == 404


def test_get_node_with_unknown_table_returns_400(configured_app):
    client = TestClient(configured_app["app"])
    resp = client.get("/nodes/Bogus/abc")
    assert resp.status_code == 400
