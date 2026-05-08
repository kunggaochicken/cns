from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.gate_items import build_gate_items_router
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import GateItemNode
from app.events.bus import EventBus


@pytest.fixture
def configured_app(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    nodes = NodeRepository(conn)
    bus = EventBus()
    g1 = GateItemNode(prompt="ship preview?", urgency="high")
    g2 = GateItemNode(prompt="send email?", urgency="medium")
    nodes.create(g1)
    nodes.create(g2)
    app = FastAPI()
    app.include_router(build_gate_items_router(nodes=nodes, conn=conn, bus=bus))
    yield {"app": app, "g1": g1, "bus": bus}
    conn.close()


def test_list_unresolved_gate_items(configured_app):
    client = TestClient(configured_app["app"])
    resp = client.get("/gate-items")
    body = resp.json()
    assert len(body) == 2
    # Highest urgency first
    assert body[0]["urgency"] == "high"


def test_resolve_writes_decision_and_marks_resolved(configured_app):
    g1 = configured_app["g1"]
    client = TestClient(configured_app["app"])
    resp = client.post(
        f"/gate-items/{g1.id}/resolve",
        json={"decision": "approved", "reasoning": "looks good"},
    )
    assert resp.status_code == 200

    # Now should not appear in unresolved list
    list_resp = client.get("/gate-items")
    ids = {g["id"] for g in list_resp.json()}
    assert g1.id not in ids


def test_resolve_invalid_decision_returns_422(configured_app):
    g1 = configured_app["g1"]
    client = TestClient(configured_app["app"])
    resp = client.post(
        f"/gate-items/{g1.id}/resolve",
        json={"decision": "maybe", "reasoning": "?"},
    )
    assert resp.status_code == 422
