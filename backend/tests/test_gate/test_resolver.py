import asyncio
from pathlib import Path

import httpx
import pytest
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import GateItemNode
from app.events.bus import EventBus
from app.events.schemas import GraphChanged
from app.gate.api import build_gate_router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def deps(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    schema_dir = Path(__file__).parents[2] / "kuzu_schema"
    conn.bootstrap_schema(schema_dir)
    nodes = NodeRepository(conn)
    bus = EventBus()
    yield {"conn": conn, "nodes": nodes, "bus": bus}
    conn.close()


def _make_app(deps) -> FastAPI:
    app = FastAPI()
    app.include_router(build_gate_router(deps["conn"], deps["bus"]))
    return app


def test_resolve_returns_404_for_unknown(deps):
    client = TestClient(_make_app(deps))
    response = client.post(
        "/gate/g_missing/resolve",
        json={"decision": "approved", "reasoning": "looks good"},
    )
    assert response.status_code == 404


def test_resolve_rejects_unknown_decision(deps):
    gate = GateItemNode(prompt="approve?", urgency="urgent")
    deps["nodes"].create(gate)
    client = TestClient(_make_app(deps))
    response = client.post(
        f"/gate/{gate.id}/resolve",
        json={"decision": "maybe", "reasoning": "x"},
    )
    assert response.status_code == 422


def test_resolve_records_decision_and_returns_ok(deps):
    gate = GateItemNode(prompt="approve?", urgency="urgent")
    deps["nodes"].create(gate)
    client = TestClient(_make_app(deps))

    response = client.post(
        f"/gate/{gate.id}/resolve",
        json={"decision": "approved", "reasoning": "looks good"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    rows = deps["conn"].query(
        "MATCH (g:GateItem) WHERE g.id = $id "
        "RETURN g.decision AS decision, g.reasoning AS reasoning, "
        "g.resolved_at AS resolved_at",
        {"id": gate.id},
    )
    assert rows[0]["decision"] == "approved"
    assert rows[0]["reasoning"] == "looks good"
    assert rows[0]["resolved_at"] is not None


async def test_resolve_emits_graph_changed_event(deps):
    gate = GateItemNode(prompt="approve?", urgency="urgent")
    deps["nodes"].create(gate)

    received: list[GraphChanged] = []

    async def handler(event: GraphChanged):
        received.append(event)

    deps["bus"].subscribe("graph.changed", handler)

    app = _make_app(deps)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/gate/{gate.id}/resolve",
            json={"decision": "vetoed", "reasoning": "nope"},
        )
    assert response.status_code == 200

    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0].change_type == "node_updated"
    assert received[0].node_id == gate.id
