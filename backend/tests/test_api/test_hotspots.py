from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.hotspots import build_hotspots_router
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
    bet1 = BetNode(slug="hot", title="Hot bet", vault_path="x.md", owner="cto")
    bet2 = BetNode(slug="cold", title="Cold bet", vault_path="y.md", owner="cto")
    nodes.create(bet1)
    nodes.create(bet2)
    # 5 thoughts pointing to bet1 (hot), 1 thought pointing to bet2 (cold)
    for i in range(5):
        t = ThoughtNode(content=f"t{i}", source="cli")
        nodes.create(t)
        edges.create(
            EdgeRecord(
                from_id=t.id,
                from_type=NodeType.THOUGHT,
                to_id=bet1.id,
                to_type=NodeType.BET,
                edge_type="sparred-against",
            )
        )
    t = ThoughtNode(content="x", source="cli")
    nodes.create(t)
    edges.create(
        EdgeRecord(
            from_id=t.id,
            from_type=NodeType.THOUGHT,
            to_id=bet2.id,
            to_type=NodeType.BET,
            edge_type="sparred-against",
        )
    )
    app = FastAPI()
    app.include_router(build_hotspots_router(conn=conn))
    yield {"app": app, "hot": bet1, "cold": bet2}
    conn.close()


def test_hotspots_ranks_by_recent_edge_count(configured_app):
    client = TestClient(configured_app["app"])
    resp = client.get("/hotspots?limit=2")
    body = resp.json()
    assert len(body) <= 2
    # Hot bet should be first
    assert body[0]["id"] == configured_app["hot"].id
    assert body[0]["edge_count"] >= 5
