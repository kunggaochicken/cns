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
