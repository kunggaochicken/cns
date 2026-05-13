from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.graph import build_graph_router
from app.db.edges import EdgeRepository
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import BetNode, EdgeRecord, NodeType, ThoughtNode


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


def test_graph_state_preserves_zero_confidence_edges(tmp_path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    schema_dir = Path(__file__).parents[2] / "kuzu_schema"
    conn.bootstrap_schema(schema_dir)
    nodes = NodeRepository(conn)
    edges = EdgeRepository(conn)

    thought = ThoughtNode(content="a", source="web")
    bet = BetNode(
        slug="zero-conf",
        title="Zero Conf",
        vault_path="Brain/Bets/bet_zero_conf.md",
        owner="ceo",
    )
    nodes.create(thought)
    nodes.create(bet)
    edges.create(
        EdgeRecord(
            from_id=thought.id,
            from_type=NodeType.THOUGHT,
            to_id=bet.id,
            to_type=NodeType.BET,
            edge_type="caused-by",
            confidence=0.0,
        )
    )

    app = FastAPI()
    app.include_router(build_graph_router(conn))
    client = TestClient(app)
    body = client.get("/graph/state").json()
    conn.close()

    matching = [
        e for e in body["edges"] if e["from_id"] == thought.id and e["to_id"] == bet.id
    ]
    assert matching, "expected the zero-confidence edge in /graph/state"
    assert matching[0]["confidence"] == 0.0


def test_graph_thought_metadata_deserializes_to_dict(tmp_path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    schema_dir = Path(__file__).parents[2] / "kuzu_schema"
    conn.bootstrap_schema(schema_dir)
    nodes = NodeRepository(conn)

    thought = ThoughtNode(content="meta", source="web", metadata={"k": "v"})
    nodes.create(thought)

    app = FastAPI()
    app.include_router(build_graph_router(conn))
    client = TestClient(app)

    state = client.get("/graph/state").json()
    payload = next(n for n in state["nodes"] if n.get("id") == thought.id)
    assert isinstance(payload["metadata"], dict)
    assert payload["metadata"] == {"k": "v"}

    detail = client.get(f"/graph/nodes/{thought.id}").json()
    assert isinstance(detail["metadata"], dict)
    assert detail["metadata"] == {"k": "v"}

    conn.close()
