import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.webhooks.github import build_github_webhook_router
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.events.bus import EventBus

SECRET = "github-test-secret"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


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
        build_github_webhook_router(
            nodes=nodes, vec=vec, bus=bus, embedder=embedder, secret=SECRET
        )
    )
    yield app, bus
    vec.close()
    conn.close()


def test_github_push_event_captures_thought(app_and_bus):
    app, _ = app_and_bus
    payload = {
        "ref": "refs/heads/main",
        "repository": {"full_name": "kunggao/gigabrain"},
        "head_commit": {
            "id": "abc123",
            "message": "feat(api): ship the thing",
            "author": {"name": "James"},
        },
    }
    body = json.dumps(payload).encode()
    with TestClient(app) as client:
        r = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "x-hub-signature-256": _sign(body),
                "x-github-event": "push",
                "content-type": "application/json",
            },
        )
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "sparring"
    assert out["node_id"].startswith("t_")


def test_github_pull_request_opened_captures_thought(app_and_bus):
    app, _ = app_and_bus
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "title": "Add capture CLI",
            "body": "Implements Plan 04 PR A.",
            "html_url": "https://github.com/kunggao/gigabrain/pull/42",
            "user": {"login": "kunggao"},
        },
        "repository": {"full_name": "kunggao/gigabrain"},
    }
    body = json.dumps(payload).encode()
    with TestClient(app) as client:
        r = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "x-hub-signature-256": _sign(body),
                "x-github-event": "pull_request",
                "content-type": "application/json",
            },
        )
    assert r.status_code == 200
    assert r.json()["status"] == "sparring"


def test_github_rejects_invalid_signature(app_and_bus):
    app, _ = app_and_bus
    body = b"{}"
    with TestClient(app) as client:
        r = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "x-hub-signature-256": "sha256=deadbeef",
                "x-github-event": "push",
            },
        )
    assert r.status_code == 401


def test_github_rejects_missing_signature(app_and_bus):
    app, _ = app_and_bus
    body = b"{}"
    with TestClient(app) as client:
        r = client.post(
            "/webhooks/github",
            content=body,
            headers={"x-github-event": "push"},
        )
    assert r.status_code == 401


def test_github_ignores_unhandled_event_types(app_and_bus):
    app, _ = app_and_bus
    body = b"{}"
    with TestClient(app) as client:
        r = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "x-hub-signature-256": _sign(body),
                "x-github-event": "ping",
            },
        )
    assert r.status_code == 200
    assert r.json() == {"status": "ignored"}
