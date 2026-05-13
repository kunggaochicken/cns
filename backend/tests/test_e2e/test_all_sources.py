"""Plan 04: every source adapter funnels into /capture identically."""

import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.webhooks.github import build_github_webhook_router
from app.api.webhooks.linear import build_linear_webhook_router
from app.capture.api import build_capture_router
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.vector import VectorStore
from app.events.bus import EventBus


@pytest.fixture
def wired_app(tmp_path: Path):
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

    app = FastAPI()
    app.include_router(
        build_capture_router(nodes=nodes, vec=vec, bus=bus, embedder=embedder)
    )
    app.include_router(
        build_linear_webhook_router(
            nodes=nodes, vec=vec, bus=bus, embedder=embedder, secret="lin-secret"
        )
    )
    app.include_router(
        build_github_webhook_router(
            nodes=nodes, vec=vec, bus=bus, embedder=embedder, secret="gh-secret"
        )
    )

    yield app, nodes
    vec.close()
    conn.close()


def test_all_three_sources_produce_thoughts_with_correct_source(wired_app):
    app, nodes = wired_app

    with TestClient(app) as client:
        r = client.post("/capture", json={"content": "from cli/web", "source": "cli"})
        assert r.status_code == 200

        lin_payload = json.dumps(
            {
                "action": "create",
                "type": "Issue",
                "data": {"id": "L1", "identifier": "GIG-1", "title": "from linear"},
            }
        ).encode()
        lin_sig = hmac.new(b"lin-secret", lin_payload, hashlib.sha256).hexdigest()
        r = client.post(
            "/webhooks/linear",
            content=lin_payload,
            headers={
                "linear-signature": lin_sig,
                "content-type": "application/json",
            },
        )
        assert r.status_code == 200

        gh_payload = json.dumps(
            {
                "ref": "refs/heads/main",
                "repository": {"full_name": "k/g"},
                "head_commit": {"id": "deadbeefcafe", "message": "from github"},
            }
        ).encode()
        gh_sig = (
            "sha256=" + hmac.new(b"gh-secret", gh_payload, hashlib.sha256).hexdigest()
        )
        r = client.post(
            "/webhooks/github",
            content=gh_payload,
            headers={
                "x-hub-signature-256": gh_sig,
                "x-github-event": "push",
                "content-type": "application/json",
            },
        )
        assert r.status_code == 200

    rows = nodes.conn.query(
        "MATCH (t:Thought) RETURN t.source AS source, t.content AS content"
    )
    sources = sorted([r["source"] for r in rows])
    assert sources == ["cli", "github", "linear"]
