from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.search import build_search_router
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import BetNode
from app.db.vector import VectorStore


@pytest.fixture
def configured_app(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    nodes.create(
        BetNode(
            slug="auth-pivot", title="Pivot to OAuth", vault_path="x.md", owner="cto"
        )
    )
    nodes.create(
        BetNode(slug="ui-redesign", title="Redesign UI", vault_path="y.md", owner="cto")
    )
    vec = VectorStore(str(tmp_path / "v.sqlite"), dim=4)
    vec.connect()
    embedder = AsyncMock()
    embedder.embed.return_value = [1.0, 0.0, 0.0, 0.0]
    embedder.dim = 4

    app = FastAPI()
    app.include_router(build_search_router(conn=conn, vec=vec, embedder=embedder))
    yield app
    vec.close()
    conn.close()


def test_text_search_returns_matching_bet(configured_app):
    client = TestClient(configured_app)
    resp = client.get("/search?q=oauth&mode=text")
    body = resp.json()
    assert any(
        "OAuth" in n.get("summary", "") or n.get("slug") == "auth-pivot" for n in body
    )


def test_text_search_no_match_returns_empty(configured_app):
    client = TestClient(configured_app)
    resp = client.get("/search?q=zzznomatch&mode=text")
    assert resp.status_code == 200
    assert resp.json() == []


def test_vector_search_returns_hits(tmp_path):
    """Vector mode embeds the query, searches the vec index, and resolves table types."""
    conn = KuzuConnection(str(tmp_path / "vsearch.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)

    vec = VectorStore(str(tmp_path / "vsearch.sqlite"), dim=4)
    vec.connect()

    # Create a Bet and seed a vector under the bet's node id (router contract:
    # vec keys are node ids — see app/capture/normalizer.py).
    bet = BetNode(
        slug="vec-target",
        title="Vector target",
        vault_path="x.md",
        owner="cto",
    )
    nodes.create(bet)
    vec.upsert(bet.id, [1.0, 0.0, 0.0, 0.0])

    # Mock embedder returns a vector close to the seeded one
    embedder = AsyncMock()
    embedder.embed.return_value = [0.99, 0.01, 0.0, 0.0]
    embedder.dim = 4

    app = FastAPI()
    app.include_router(build_search_router(conn=conn, vec=vec, embedder=embedder))
    client = TestClient(app)

    resp = client.get("/search?q=anything&mode=vector&limit=5")
    assert resp.status_code == 200
    body = resp.json()
    embedder.embed.assert_awaited_once_with("anything")
    assert any(
        r["id"] == bet.id and r["type"] == "Bet" for r in body
    ), f"expected bet hit in vector results, got {body}"

    vec.close()
    conn.close()


def test_vector_search_no_hits_returns_empty(tmp_path):
    """Vector mode returns [] when the vector store yields no results."""
    conn = KuzuConnection(str(tmp_path / "vempty.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    vec = VectorStore(str(tmp_path / "vempty.sqlite"), dim=4)
    vec.connect()
    embedder = AsyncMock()
    embedder.embed.return_value = [1.0, 0.0, 0.0, 0.0]
    embedder.dim = 4

    app = FastAPI()
    app.include_router(build_search_router(conn=conn, vec=vec, embedder=embedder))
    client = TestClient(app)

    resp = client.get("/search?q=foo&mode=vector")
    assert resp.status_code == 200
    assert resp.json() == []

    vec.close()
    conn.close()
