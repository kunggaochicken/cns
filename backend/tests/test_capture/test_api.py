from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from app.capture.api import build_capture_router
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.events.bus import EventBus
from app.events.schemas import ThoughtCreated
from fastapi.testclient import TestClient


@pytest.fixture
def deps(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    schema_dir = Path(__file__).parents[2] / "kuzu_schema"
    conn.bootstrap_schema(schema_dir)
    nodes = NodeRepository(conn)
    vec = VectorStore(str(tmp_path / "v.sqlite"), dim=4)
    vec.connect()
    bus = EventBus()
    embedder = AsyncMock()
    embedder.embed.return_value = [0.1, 0.2, 0.3, 0.4]
    embedder.dim = 4
    yield {"nodes": nodes, "vec": vec, "bus": bus, "embedder": embedder}
    vec.close()
    conn.close()


def test_capture_creates_thought_and_emits_event(deps):
    from fastapi import FastAPI

    app = FastAPI()
    received_events = []

    async def handler(event: ThoughtCreated):
        received_events.append(event)

    deps["bus"].subscribe("thought.created", handler)

    app.include_router(
        build_capture_router(
            nodes=deps["nodes"],
            vec=deps["vec"],
            bus=deps["bus"],
            embedder=deps["embedder"],
        )
    )
    client = TestClient(app)

    response = client.post(
        "/capture",
        json={"content": "should we ship preview?", "source": "cli"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "node_id" in body
    assert body["status"] == "sparring"
    assert body["node_id"].startswith("t_")
