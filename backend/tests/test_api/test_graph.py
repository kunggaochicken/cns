from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.graph import build_graph_router
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import BetNode, ThoughtNode


@pytest.fixture
def graph_app(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    schema_dir = Path(__file__).parents[2] / "kuzu_schema"
    conn.bootstrap_schema(schema_dir)
    nodes = NodeRepository(conn)

    nodes.create(ThoughtNode(content="a thought", source="web"))
    nodes.create(
        BetNode(
            slug="ship-v1",
            title="Ship v1",
            vault_path="Brain/Bets/bet_ship_v1.md",
            owner="ceo",
        )
    )

    app = FastAPI()
    app.include_router(build_graph_router(conn))
    yield app
    conn.close()


def test_graph_state_returns_all_nodes_and_edges(graph_app):
    client = TestClient(graph_app)
    response = client.get("/graph/state")
    assert response.status_code == 200
    body = response.json()
    assert "nodes" in body and "edges" in body
    node_types = sorted({n["node_type"] for n in body["nodes"]})
    assert "bet" in node_types
    assert "thought" in node_types


def test_graph_state_includes_node_fields(graph_app):
    client = TestClient(graph_app)
    response = client.get("/graph/state")
    bet = next(n for n in response.json()["nodes"] if n["node_type"] == "bet")
    assert bet["slug"] == "ship-v1"
    assert bet["title"] == "Ship v1"


def test_graph_node_by_id_returns_full_detail(graph_app):
    client = TestClient(graph_app)
    bet = next(
        n for n in client.get("/graph/state").json()["nodes"] if n["node_type"] == "bet"
    )
    response = client.get(f"/graph/nodes/{bet['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["node_type"] == "bet"
    assert body["slug"] == "ship-v1"
    assert "edges_in" in body
    assert "edges_out" in body


def test_graph_node_by_id_returns_404_for_unknown(graph_app):
    client = TestClient(graph_app)
    response = client.get("/graph/nodes/does_not_exist")
    assert response.status_code == 404
