# backend/tests/test_api/test_webhooks/test_linear.py
import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.webhooks.linear import build_linear_webhook_router
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.events.bus import EventBus

SECRET = "linear-test-secret"


def _sign(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def app_and_bus(tmp_path: Path):
    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    schema_dir = Path(__file__).parents[3] / "kuzu_schema"
    conn.bootstrap_schema(schema_dir)
    nodes = NodeRepository(conn)
    vec = VectorStore(str(tmp_path / "v.sqlite"), dim=4)
    vec.connect()
    bus = EventBus()
    embedder = AsyncMock()
    embedder.embed.return_value = [0.1, 0.2, 0.3, 0.4]

    app = FastAPI()
    app.include_router(
        build_linear_webhook_router(
            nodes=nodes, vec=vec, bus=bus, embedder=embedder, secret=SECRET
        )
    )
    yield app, bus
    vec.close()
    conn.close()


def test_linear_create_issue_captures_thought(app_and_bus):
    app, _ = app_and_bus
    payload = {
        "action": "create",
        "type": "Issue",
        "data": {
            "id": "lin_123",
            "identifier": "GIG-42",
            "title": "Ship the brain view",
            "description": "Need to land Plan 03 before Friday.",
            "team": {"key": "GIG"},
            "url": "https://linear.app/team/issue/GIG-42",
        },
    }
    body = json.dumps(payload).encode()
    with TestClient(app) as client:
        r = client.post(
            "/webhooks/linear",
            content=body,
            headers={
                "linear-signature": _sign(body),
                "content-type": "application/json",
            },
        )
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "sparring"
    assert out["node_id"].startswith("t_")


def test_linear_rejects_invalid_signature(app_and_bus):
    app, _ = app_and_bus
    payload = {"action": "create", "type": "Issue", "data": {"id": "x", "title": "y"}}
    body = json.dumps(payload).encode()
    with TestClient(app) as client:
        r = client.post(
            "/webhooks/linear",
            content=body,
            headers={
                "linear-signature": "deadbeef",
                "content-type": "application/json",
            },
        )
    assert r.status_code == 401


def test_linear_rejects_missing_signature(app_and_bus):
    app, _ = app_and_bus
    payload = {"action": "create", "type": "Issue", "data": {"id": "x", "title": "y"}}
    body = json.dumps(payload).encode()
    with TestClient(app) as client:
        r = client.post(
            "/webhooks/linear",
            content=body,
            headers={"content-type": "application/json"},
        )
    assert r.status_code == 401


def test_linear_ignores_non_issue_events(app_and_bus):
    app, _ = app_and_bus
    payload = {"action": "create", "type": "Comment", "data": {"id": "c", "body": "hi"}}
    body = json.dumps(payload).encode()
    with TestClient(app) as client:
        r = client.post(
            "/webhooks/linear",
            content=body,
            headers={
                "linear-signature": _sign(body),
                "content-type": "application/json",
            },
        )
    # 200 with ignored:true keeps Linear from retrying; we just don't capture it.
    assert r.status_code == 200
    assert r.json() == {"status": "ignored"}
